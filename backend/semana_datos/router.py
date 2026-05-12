"""
Módulo "La Semana en Datos": scrape de informes BCR + generación de portadas
YouTube/Reel + upload del programa a YouTube + edición de recortes (apagada
por OOM en Render free tier, ver feature flag al final).
"""
import os
import threading
import time
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from auth import require_auth
from config import UPLOADS_DIR
from utils.informes import fetch_informe, InformeNotFound
from utils.semana_datos import (
    generate_portada_yt, generate_portada_reel,
    build_title, build_description,
)
from utils.youtube_upload import (
    extract_drive_file_id, get_drive_file_metadata,
    upload_program_to_youtube, SEMANA_DATOS_PLAYLIST_ID,
)


router = APIRouter(prefix="/api/semana-datos", dependencies=[Depends(require_auth)])


# ---------------------------------------------------------
# Scrape de informes (og:title + og:description)
# ---------------------------------------------------------
class ScrapeRequest(BaseModel):
    urls: List[str]


class PreviewRequest(BaseModel):
    titulos: List[str]
    copetes: List[str] = []


@router.post("/scrape")
def scrape_informes(req: ScrapeRequest):
    urls = [u.strip() for u in req.urls if u and u.strip()]
    if not 1 <= len(urls) <= 2:
        raise HTTPException(status_code=400, detail="Se esperan 1 o 2 URLs")

    informes = []
    for url in urls:
        try:
            informes.append(fetch_informe(url))
        except InformeNotFound as e:
            raise HTTPException(status_code=400, detail=f"{url}: {e}")
    return {"informes": informes}


# ---------------------------------------------------------
# Generación de portadas (preview en vivo)
# ---------------------------------------------------------
@router.post("/preview-portada")
def preview_portada(req: PreviewRequest):
    titulos = [t.strip() for t in req.titulos if t and t.strip()]
    if not 1 <= len(titulos) <= 2:
        raise HTTPException(status_code=400, detail="Se esperan 1 o 2 títulos")
    try:
        png = generate_portada_yt(titulos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar portada: {e}")
    return Response(content=png, media_type="image/png")


class ReelRequest(BaseModel):
    titulo: str


@router.post("/preview-portada-reel")
def preview_portada_reel(req: ReelRequest):
    """Una portada vertical por informe (frontend llama 1 o 2 veces)."""
    titulo = (req.titulo or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="Falta el título")
    try:
        png = generate_portada_reel(titulo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar portada Reel: {e}")
    return Response(content=png, media_type="image/png")


@router.post("/preview-metadata")
def preview_metadata(req: PreviewRequest):
    return {
        "titulo": build_title(req.titulos),
        "descripcion": build_description(req.copetes),
    }


# ---------------------------------------------------------
# Validación del Drive del programa (sanity check antes del upload)
# ---------------------------------------------------------
class DriveCheckRequest(BaseModel):
    drive_url: str


@router.post("/drive-check")
def drive_check(req: DriveCheckRequest):
    file_id = extract_drive_file_id(req.drive_url)
    if not file_id:
        raise HTTPException(status_code=400, detail="No pude extraer un ID de Drive de esa URL")
    try:
        meta = get_drive_file_metadata(file_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {e}")
    mime = meta.get("mimeType", "")
    if not mime.startswith("video/"):
        raise HTTPException(status_code=400, detail=f"El archivo no es un video (mime: {mime})")
    size = int(meta.get("size") or 0)
    return {
        "file_id": file_id,
        "name": meta.get("name"),
        "mime": mime,
        "size_mb": round(size / (1024 * 1024), 1) if size else None,
    }


# ---------------------------------------------------------
# Upload del programa completo a YouTube
# ---------------------------------------------------------
class UploadRequest(BaseModel):
    drive_url: str
    titulos_portada: List[str]
    titulo_youtube: str
    descripcion: str


@router.post("/upload-youtube")
def upload_youtube(req: UploadRequest):
    """Descarga el video de Drive, lo sube a YouTube con la portada generada
    al momento (usando titulos_portada) y lo agrega a la playlist del ciclo."""
    file_id = extract_drive_file_id(req.drive_url)
    if not file_id:
        raise HTTPException(status_code=400, detail="No pude extraer un ID de Drive de esa URL")

    titulos_portada = [t.strip() for t in req.titulos_portada if t and t.strip()]
    if not 1 <= len(titulos_portada) <= 2:
        raise HTTPException(status_code=400, detail="Se esperan 1 o 2 títulos para la portada")
    if not req.titulo_youtube.strip():
        raise HTTPException(status_code=400, detail="Falta el título de YouTube")
    if not req.descripcion.strip():
        raise HTTPException(status_code=400, detail="Falta la descripción")

    # Server-side regen de la portada — no confiamos en el state del frontend.
    try:
        portada_png = generate_portada_yt(titulos_portada)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar la portada: {e}")

    try:
        result = upload_program_to_youtube(
            drive_file_id=file_id,
            title=req.titulo_youtube.strip(),
            description=req.descripcion.strip(),
            thumbnail_bytes=portada_png,
            privacy="public",
            playlist_id=SEMANA_DATOS_PLAYLIST_ID,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el upload a YouTube: {e}")

    return result


# ---------------------------------------------------------
# Editor de recortes (job tracking en memoria + thread daemon)
# Apagado en la UI por OOM en Render free tier — el endpoint sigue.
# ---------------------------------------------------------
class EditClipRequest(BaseModel):
    drive_url: str


_clip_jobs: dict = {}


def _run_edit_clip(job_id: str, drive_url: str):
    job = _clip_jobs[job_id]
    input_path = None
    try:
        job["stage"] = "Validando archivo en Drive…"

        file_id = extract_drive_file_id(drive_url)
        if not file_id:
            raise ValueError("No pude extraer un ID de Drive de esa URL")

        meta = get_drive_file_metadata(file_id)
        if not (meta.get("mimeType") or "").startswith("video/"):
            raise ValueError(f"El archivo no es un video (mime: {meta.get('mimeType')})")
        job["drive_file_name"] = meta.get("name")

        job["stage"] = "Descargando recorte de Drive…"
        from utils.youtube_upload import download_drive_file
        input_path = os.path.join(UPLOADS_DIR, f"clip_in_{job_id}.mp4")
        download_drive_file(file_id, input_path)

        output_filename = f"reel_{job_id}.mp4"
        output_path = os.path.join(UPLOADS_DIR, output_filename)

        job["stage"] = "Transcribiendo audio y componiendo video…"
        from utils.clip_editor import edit_clip
        result = edit_clip(input_path, output_path)

        job.update({
            "status": "done",
            "stage": "Listo",
            "url": f"/static/uploads/{output_filename}",
            "filename": output_filename,
            "duration": result.get("duration"),
            "subtitle_count": result.get("subtitle_count"),
            "finished_at": time.time(),
        })
    except Exception as e:
        import traceback
        print(f"[edit-clip job={job_id}] ERROR: {e}\n{traceback.format_exc()}")
        job.update({
            "status": "error",
            "error": str(e),
            "finished_at": time.time(),
        })
    finally:
        if input_path:
            try:
                os.remove(input_path)
            except Exception:
                pass


def _gc_old_jobs(ttl_seconds: int = 3600):
    cutoff = time.time() - ttl_seconds
    for jid in list(_clip_jobs.keys()):
        started = _clip_jobs[jid].get("started_at", 0)
        if started and started < cutoff:
            _clip_jobs.pop(jid, None)


@router.post("/edit-clip")
def edit_clip_endpoint(req: EditClipRequest):
    _gc_old_jobs()
    job_id = uuid.uuid4().hex
    _clip_jobs[job_id] = {
        "status": "processing",
        "stage": "Iniciando…",
        "started_at": time.time(),
    }
    t = threading.Thread(target=_run_edit_clip, args=(job_id, req.drive_url), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "processing"}


@router.get("/edit-clip/status/{job_id}")
def edit_clip_status(job_id: str):
    job = _clip_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado")
    return job

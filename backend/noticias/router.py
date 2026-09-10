"""
Módulo Noticias — Más BCR.

Dos routers:
  - `router`  (/api/noticias)  → API JSON del ADMIN (CRUD + subir imágenes), con auth.
  - `site`    (/noticias/...)  → sitio PÚBLICO server-rendered (SEO), sin auth.

El admin (SPA) vive en static/noticias/admin.html y se sirve desde app.py.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Optional

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import require_auth
from config import CLOUDINARY_ENABLED, MASBCR_TABLERO_URL, UPLOADS_DIR
from database import get_db
from noticias import render
from noticias.models import (
    CATEGORIAS, KIT_CATEGORIAS, _KIT_NOMBRE, _KIT_SLUGS,
    MediaAsset, MediaAssetIn, Noticia, NoticiaIn, Video, VideoIn,
)

_YT_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/|v/))([A-Za-z0-9_-]{11})")


def _yt_id(url: str) -> Optional[str]:
    m = _YT_RE.search(url or "")
    if m:
        return m.group(1)
    s = (url or "").strip()
    return s if re.fullmatch(r"[A-Za-z0-9_-]{11}", s) else None


# ===========================================================================
# Helpers
# ===========================================================================
def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:80] or "nota"


def _unique_slug(db: Session, base: str, exclude_id: Optional[int] = None) -> str:
    slug = base
    i = 2
    while True:
        q = db.query(Noticia).filter(Noticia.slug == slug)
        if exclude_id is not None:
            q = q.filter(Noticia.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{i}"
        i += 1


def _to_dict(n: Noticia) -> dict[str, Any]:
    return {
        "id": n.id, "slug": n.slug, "titulo": n.titulo, "bajada": n.bajada,
        "cuerpo": n.cuerpo, "imagen_portada": n.imagen_portada, "categoria": n.categoria,
        "estado": n.estado,
        "fecha_pub": n.fecha_pub.isoformat() if n.fecha_pub else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


# ===========================================================================
# API del admin (con auth)
# ===========================================================================
router = APIRouter(prefix="/api/noticias", dependencies=[Depends(require_auth)])


@router.get("")
def listar_admin(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Todas las notas (incluye borradores), más recientes primero."""
    rows = db.query(Noticia).order_by(Noticia.created_at.desc()).all()
    return {"categorias": CATEGORIAS, "noticias": [_to_dict(n) for n in rows]}


@router.get("/{nid}")
def obtener(nid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.query(Noticia).filter(Noticia.id == nid).first()
    if n is None:
        raise HTTPException(404, "Noticia no encontrada")
    return _to_dict(n)


@router.post("")
def crear(payload: NoticiaIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not payload.titulo.strip():
        raise HTTPException(400, "El título es obligatorio")
    n = Noticia(
        slug=_unique_slug(db, _slugify(payload.titulo)),
        titulo=payload.titulo.strip(),
        bajada=payload.bajada,
        cuerpo=payload.cuerpo,
        imagen_portada=payload.imagen_portada,
        categoria=payload.categoria,
        estado=payload.estado or "borrador",
    )
    if n.estado == "publicado":
        n.fecha_pub = datetime.utcnow()
    db.add(n)
    db.commit()
    db.refresh(n)
    return _to_dict(n)


@router.put("/{nid}")
def actualizar(nid: int, payload: NoticiaIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.query(Noticia).filter(Noticia.id == nid).first()
    if n is None:
        raise HTTPException(404, "Noticia no encontrada")
    n.titulo = payload.titulo.strip() or n.titulo
    n.bajada = payload.bajada
    n.cuerpo = payload.cuerpo
    n.imagen_portada = payload.imagen_portada
    n.categoria = payload.categoria
    # El slug se mantiene estable (SEO). Sólo cambia el estado/fecha.
    nuevo_estado = payload.estado or n.estado
    if nuevo_estado == "publicado" and n.fecha_pub is None:
        n.fecha_pub = datetime.utcnow()  # primera publicación
    n.estado = nuevo_estado
    db.commit()
    db.refresh(n)
    return _to_dict(n)


@router.delete("/{nid}")
def borrar(nid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    n = db.query(Noticia).filter(Noticia.id == nid).first()
    if n is None:
        raise HTTPException(404, "Noticia no encontrada")
    db.delete(n)
    db.commit()
    return {"ok": True}


_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@router.post("/upload")
async def subir_imagen(file: UploadFile = File(...)) -> dict[str, Any]:
    """Sube una imagen (portada o dentro del cuerpo) a Cloudinary; fallback local."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _IMG_EXT:
        raise HTTPException(400, "Formato no permitido. Subí JPG, PNG, WEBP o GIF.")

    if CLOUDINARY_ENABLED:
        try:
            result = cloudinary.uploader.upload(
                file.file, folder="masbcr-noticias", resource_type="image",
                use_filename=True, unique_filename=True,
            )
            if result.get("secure_url"):
                return {"url": result["secure_url"]}
        except Exception as e:  # noqa: BLE001
            print(f"Error subiendo imagen noticia a Cloudinary, fallback local: {e}")
            try:
                file.file.seek(0)
            except Exception:
                pass

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    filename = f"noticia_{uuid.uuid4()}{ext}"
    with open(os.path.join(UPLOADS_DIR, filename), "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    return {"url": f"/static/uploads/{filename}"}


@router.post("/importar-wp")
async def importar_wp(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Importa noticias desde uno o más XML (WXR) exportados de WordPress.
    Idempotente: crea sólo las notas cuyo slug no exista todavía. Las imágenes
    quedan apuntando al host de WP hasta que se corra el re-hosting."""
    from noticias.importer import parse_wxr, importar_posts

    tmpdir = tempfile.mkdtemp()
    paths = []
    try:
        for i, f in enumerate(files):
            p = os.path.join(tmpdir, f.filename or f"wxr_{i}.xml")
            with open(p, "wb") as buf:
                buf.write(await f.read())
            paths.append(p)
        posts = parse_wxr(paths)
        return importar_posts(db, posts)
    finally:
        for p in paths:
            try:
                os.remove(p)
            except Exception:
                pass


# ===========================================================================
# API del Kit Multimedia (con auth) — prefijo propio para no chocar con /{nid}
# ===========================================================================
kit_api = APIRouter(prefix="/api/kit", dependencies=[Depends(require_auth)])


@kit_api.get("")
def kit_listar(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(MediaAsset).order_by(MediaAsset.orden.asc(), MediaAsset.created_at.desc()).all()
    return {
        "categorias": KIT_CATEGORIAS,
        "assets": [
            {"id": a.id, "kit_cat": a.kit_cat, "url": a.url, "titulo": a.titulo}
            for a in rows
        ],
    }


@kit_api.post("")
def kit_crear(payload: MediaAssetIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if payload.kit_cat not in _KIT_SLUGS:
        raise HTTPException(400, "Categoría de kit inválida")
    if not payload.url:
        raise HTTPException(400, "Falta la URL de la imagen")
    a = MediaAsset(kit_cat=payload.kit_cat, url=payload.url, titulo=payload.titulo)
    db.add(a)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "kit_cat": a.kit_cat, "url": a.url, "titulo": a.titulo}


@kit_api.delete("/{aid}")
def kit_borrar(aid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.query(MediaAsset).filter(MediaAsset.id == aid).first()
    if a is None:
        raise HTTPException(404, "Recurso no encontrado")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ===========================================================================
# API de Videos (con auth)
# ===========================================================================
videos_api = APIRouter(prefix="/api/videos", dependencies=[Depends(require_auth)])


@videos_api.get("")
def videos_listar(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(Video).order_by(Video.orden.asc(), Video.created_at.desc()).all()
    return {"videos": [{"id": v.id, "youtube_id": v.youtube_id, "titulo": v.titulo} for v in rows]}


@videos_api.post("")
def videos_crear(payload: VideoIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    yid = _yt_id(payload.url)
    if not yid:
        raise HTTPException(400, "No pude reconocer el video de YouTube. Pegá la URL completa.")
    v = Video(youtube_id=yid, titulo=payload.titulo)
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"id": v.id, "youtube_id": v.youtube_id, "titulo": v.titulo}


@videos_api.delete("/{vid}")
def videos_borrar(vid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    v = db.query(Video).filter(Video.id == vid).first()
    if v is None:
        raise HTTPException(404, "Video no encontrado")
    db.delete(v)
    db.commit()
    return {"ok": True}


# ===========================================================================
# Sitio público (server-rendered, sin auth)
# ===========================================================================
site = APIRouter()


def _canonical(request: Request, path: str) -> str:
    return str(request.base_url).rstrip("/") + path


@site.get("/noticias", include_in_schema=False)
async def home_redirect():
    return RedirectResponse(url="/noticias/", status_code=307)


@site.get("/noticias/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Noticia).filter(Noticia.estado == "publicado")
        .order_by(Noticia.fecha_pub.desc()).limit(13).all()
    )
    videos = db.query(Video).order_by(Video.orden.asc(), Video.created_at.desc()).limit(4).all()
    title, body = render.render_home(rows, videos)
    html = render.base_page(
        title=title,
        description="Agencia de noticias de la Bolsa de Comercio de Rosario.",
        body=body,
        canonical=_canonical(request, "/noticias/"),
        og_image=rows[0].imagen_portada if rows else None,
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})


@site.get("/noticias/nota/{slug}", response_class=HTMLResponse)
async def nota(slug: str, request: Request, db: Session = Depends(get_db)):
    n = db.query(Noticia).filter(Noticia.slug == slug, Noticia.estado == "publicado").first()
    if n is None:
        raise HTTPException(404, "Nota no encontrada")
    relacionadas = (
        db.query(Noticia)
        .filter(Noticia.estado == "publicado", Noticia.id != n.id)
        .order_by(Noticia.fecha_pub.desc()).limit(5).all()
    )
    canonical = _canonical(request, f"/noticias/nota/{n.slug}")
    body = render.render_article(n, relacionadas, canonical)
    html = render.base_page(
        title=f"{n.titulo} — Más BCR",
        description=(n.bajada or n.titulo)[:200],
        body=body,
        canonical=canonical,
        og_image=n.imagen_portada,
        og_type="article",
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})


@site.get("/noticias/categoria/{categoria}", response_class=HTMLResponse)
async def categoria(categoria: str, request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Noticia)
        .filter(Noticia.estado == "publicado", Noticia.categoria == categoria)
        .order_by(Noticia.fecha_pub.desc()).limit(60).all()
    )
    body = render.render_lista(categoria, rows)
    html = render.base_page(
        title=f"{categoria} — Más BCR",
        description=f"Noticias de {categoria} — Bolsa de Comercio de Rosario.",
        body=body,
        canonical=_canonical(request, f"/noticias/categoria/{categoria}"),
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})


@site.get("/noticias/kit", response_class=HTMLResponse)
async def kit_index(request: Request, db: Session = Depends(get_db)):
    rows = db.query(MediaAsset).order_by(MediaAsset.orden.asc(), MediaAsset.created_at.desc()).all()
    cats = []
    for c in KIT_CATEGORIAS:
        assets = [a for a in rows if a.kit_cat == c["slug"]]
        cats.append({
            "slug": c["slug"], "nombre": c["nombre"], "desc": c["desc"],
            "count": len(assets),
            "thumb": assets[0].url if assets else None,
        })
    body = render.render_kit_index(cats)
    html = render.base_page(
        title="Kit Multimedia — Más BCR",
        description="Biblioteca de imágenes y videos de libre uso para medios de comunicación.",
        body=body,
        canonical=_canonical(request, "/noticias/kit"),
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})


@site.get("/noticias/tablero", response_class=HTMLResponse)
async def tablero(request: Request):
    body = render.render_tablero(MASBCR_TABLERO_URL)
    html = render.base_page(
        title="Tablero de Cultivos — Más BCR",
        description="Datos estadísticos de las campañas de soja, trigo y maíz de los últimos 10 años.",
        body=body,
        canonical=_canonical(request, "/noticias/tablero"),
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=300"})


@site.get("/noticias/kit/{cat}", response_class=HTMLResponse)
async def kit_gallery(cat: str, request: Request, db: Session = Depends(get_db)):
    if cat not in _KIT_SLUGS:
        raise HTTPException(404, "Galería no encontrada")
    assets = (
        db.query(MediaAsset).filter(MediaAsset.kit_cat == cat)
        .order_by(MediaAsset.orden.asc(), MediaAsset.created_at.desc()).all()
    )
    nombre = _KIT_NOMBRE.get(cat, cat)
    body = render.render_kit_gallery(nombre, assets)
    html = render.base_page(
        title=f"Kit Multimedia · {nombre} — Más BCR",
        description=f"Imágenes de {nombre} — Kit Multimedia de la BCR.",
        body=body,
        canonical=_canonical(request, f"/noticias/kit/{cat}"),
    )
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=120"})

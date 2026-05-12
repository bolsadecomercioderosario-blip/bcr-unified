"""
Módulo Lluvias: genera el reporte de precipitaciones (texto + mapa + video
animado) y publica el tweet en @BolsaRosario.
"""
import os
import time

from fastapi import APIRouter, BackgroundTasks

from config import UPLOADS_DIR
from common import PublicarTwitterRequest, publish_to_twitter
from scraper import get_rainfall_metadata, create_animated_video_from_data


router = APIRouter(prefix="/api/lluvias")

# Estado global del video animado para esta instancia del worker.
# Se reinicia con el proceso — aceptable porque cada generación es on-demand.
video_status = {"ready": False, "error": None, "url": None}


def _video_generation_task(top_5, map_path):
    """Tarea en background que renderea el video animado a partir del top-5."""
    global video_status
    video_status["ready"] = False
    video_status["error"] = None
    try:
        timestamp = int(time.time())
        filename = f"historia_lluvias_{timestamp}.mp4"
        output_path = os.path.join(UPLOADS_DIR, filename)

        # Limpiar videos antiguos para no llenar el disk
        for f in os.listdir(UPLOADS_DIR):
            if f.startswith("historia_lluvias_") and f.endswith(".mp4"):
                try: os.remove(os.path.join(UPLOADS_DIR, f))
                except Exception: pass

        create_animated_video_from_data(top_5, map_path, output_mp4=output_path)
        video_status["url"] = f"/static/uploads/{filename}"
        video_status["ready"] = True
    except Exception as e:
        print(f"Error en tarea de video: {e}")
        video_status["error"] = str(e)


@router.get("/generar_pieza")
async def generar_lluvias(background_tasks: BackgroundTasks):
    top_5, texto, imagen_url, no_lluvias = get_rainfall_metadata()

    video_enabled = not no_lluvias

    if video_enabled:
        map_local_path = os.path.join(UPLOADS_DIR, "mapa_lluvias.jpg")
        background_tasks.add_task(_video_generation_task, top_5, map_local_path)

    return {
        "texto": texto,
        "imagen_url": imagen_url,
        "video_status": "processing" if video_enabled else "disabled",
        "no_lluvias": no_lluvias,
    }


@router.get("/video_status")
def get_video_status_endpoint():
    if video_status["ready"]:
        return {"status": "ready", "video_url": video_status["url"]}
    if video_status["error"]:
        return {"status": "error", "message": video_status["error"]}
    return {"status": "processing"}


@router.post("/publicar-twitter")
def publicar_lluvias_twitter(req: PublicarTwitterRequest):
    """Publica el reporte de lluvias en @BolsaRosario con la imagen del mapa."""
    return publish_to_twitter(req.texto, req.imagen_url)

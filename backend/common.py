"""
Helpers compartidos entre módulos. Por ahora sólo lo de Twitter publishing
(usado tanto por Lluvias como por Social).
"""
import os
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from config import STATIC_DIR, UPLOADS_DIR


class PublicarTwitterRequest(BaseModel):
    texto: str
    imagen_url: Optional[str] = None  # /static/uploads/... o URL absoluta


def resolve_image_to_local_path(image_url: str) -> tuple[str, Optional[str]]:
    """Resuelve una URL de imagen a un path local listo para subir a X.
    Acepta /static/uploads/..., /static/..., y URLs absolutas http(s).
    Devuelve (path, tempfile_to_cleanup_or_None)."""
    url = image_url.strip()
    if url.startswith("/static/uploads/"):
        path = os.path.join(UPLOADS_DIR, url[len("/static/uploads/"):])
        return path, None
    if url.startswith("/static/"):
        path = os.path.join(STATIC_DIR, url[len("/static/"):])
        return path, None
    if url.startswith("http"):
        import tempfile, requests
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No se pudo descargar la imagen: {e}")
        suffix = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        f.write(r.content)
        f.close()
        return f.name, f.name
    raise HTTPException(status_code=400, detail=f"URL de imagen no soportada: {url}")


def publish_to_twitter(texto: str, imagen_url: Optional[str]) -> dict:
    """Helper compartido — Lluvias y Social lo usan para postear en @BolsaRosario."""
    from utils.twitter import post_tweet, TwitterNotConfigured

    text = (texto or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El texto está vacío")

    image_path = None
    tmp_to_remove = None
    if imagen_url:
        image_path, tmp_to_remove = resolve_image_to_local_path(imagen_url)
        if not os.path.exists(image_path):
            raise HTTPException(status_code=400, detail=f"No se encontró la imagen: {image_path}")

    try:
        return post_tweet(text=text, image_path=image_path)
    except TwitterNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"X rechazó el tweet: {e}")
    finally:
        if tmp_to_remove:
            try: os.remove(tmp_to_remove)
            except Exception: pass

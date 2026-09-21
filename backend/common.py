"""
Helpers compartidos entre módulos. Por ahora sólo lo de Twitter publishing
(usado tanto por Lluvias como por Social).
"""
import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException
from pydantic import BaseModel

from config import STATIC_DIR, UPLOADS_DIR, EXTERNAL_INTEGRATIONS_ENABLED, GOOGLE_DRIVE_ENABLED


def assert_safe_url(url: str, allowed_hosts: Optional[set] = None) -> None:
    """Guard anti-SSRF para URLs que el server va a descargar.

    - Sólo http/https.
    - Si se pasa `allowed_hosts`, el hostname debe estar en esa lista.
    - El hostname debe resolver SOLO a IPs públicas: se rechaza loopback,
      privada, link-local, reservada, multicast o no especificada (evita que
      alguien haga que el server pegue a 127.0.0.1, 169.254.169.254, 10.x, etc.).
    Levanta HTTPException(400) si algo no cumple.
    """
    p = urlparse((url or "").strip())
    if p.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL no permitida (esquema inválido)")
    host = (p.hostname or "").lower()
    if not host:
        raise HTTPException(status_code=400, detail="URL sin host")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise HTTPException(status_code=400, detail=f"Dominio no permitido: {host}")
    port = p.port or (443 if p.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception:
        raise HTTPException(status_code=400, detail="No se pudo resolver el host de la URL")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise HTTPException(status_code=400, detail="La URL apunta a una IP no permitida")


def require_external_integrations():
    """Bloquea endpoints que hablan con servicios externos (X, YouTube, Drive,
    webhooks). Se activa con la env var EXTERNAL_INTEGRATIONS_ENABLED=true.
    Mientras esté desactivado, la UI sigue intacta pero el backend responde
    503 con un mensaje claro — útil para cerrar 'puertas abiertas' hasta tener
    un entorno más seguro."""
    if not EXTERNAL_INTEGRATIONS_ENABLED:
        raise HTTPException(
            status_code=503,
            detail=(
                "Las integraciones externas (X/Twitter, YouTube, Google Drive, "
                "webhooks) están temporalmente deshabilitadas por seguridad. "
                "Contactá al admin para reactivarlas."
            ),
        )


def require_google_drive():
    """Como require_external_integrations pero SÓLO para Google Drive (crear
    carpetas de actividades + OAuth). Se activa con GOOGLE_DRIVE_ENABLED=true (o
    con el flag global). Permite prender Drive sin habilitar X/YouTube/webhooks."""
    if not GOOGLE_DRIVE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail=(
                "La integración con Google Drive está deshabilitada. "
                "Contactá al admin para activarla."
            ),
        )


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
        assert_safe_url(url)  # anti-SSRF: no IPs internas, solo http/https
        try:
            r = requests.get(url, timeout=30, allow_redirects=False)
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

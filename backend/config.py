"""
Configuración compartida entre todos los módulos del backend:
- Directorios base
- Versión de la app (commit hash en Render, "dev" en local)
- Cliente Cloudinary (si está configurado)
- NoCacheStaticFiles: StaticFiles que fuerza revalidación
- get_module_html: lee y cachea el index.html de cada módulo,
  inyectando __VERSION__ para cache-busting
"""
import os

from fastapi.staticfiles import StaticFiles


# Directorios base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)


# Versión de la app — Render expone RENDER_GIT_COMMIT con el SHA del commit.
APP_VERSION = os.environ.get("RENDER_GIT_COMMIT", "dev")[:7]


# ---------------------------------------------------------------------------
# Cloudinary (CDN para imágenes del newsletter Conectados).
# Sólo se activa si las tres env vars están presentes; si faltan, los uploads
# del newsletter caen al storage local — útil para dev y como fallback.
# ---------------------------------------------------------------------------
import cloudinary  # noqa: E402

CLOUDINARY_ENABLED = all([
    os.environ.get("CLOUDINARY_CLOUD_NAME"),
    os.environ.get("CLOUDINARY_API_KEY"),
    os.environ.get("CLOUDINARY_API_SECRET"),
])
if CLOUDINARY_ENABLED:
    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    print("Cloudinary configurado: los uploads de newsletter van al CDN.")
else:
    print("Cloudinary no configurado — los uploads se guardan localmente.")


# ---------------------------------------------------------------------------
# Static files con revalidación obligatoria — evita que el browser quede con
# CSS/JS stale después de un deploy.
# ---------------------------------------------------------------------------
class NoCacheStaticFiles(StaticFiles):
    """StaticFiles que pide al browser revalidar siempre.
    El browser usa If-Modified-Since y el server responde 304 si no cambió,
    evitando que CSS/JS queden cacheados stale después de un deploy."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


# ---------------------------------------------------------------------------
# Cache en memoria de los HTML de cada módulo. Se leen una sola vez por
# proceso y se devuelven con __VERSION__ reemplazado por APP_VERSION para
# cache-busting de assets.
# ---------------------------------------------------------------------------
_HTML_TEMPLATES: dict = {}


def get_module_html(module: str) -> str:
    """Lee y cachea el index.html de un módulo (ej. 'agenda', 'semana-datos').
    Reemplaza __VERSION__ por APP_VERSION para cache-busting de assets."""
    if module not in _HTML_TEMPLATES:
        path = os.path.join(STATIC_DIR, module, "index.html")
        with open(path, "r", encoding="utf-8") as f:
            _HTML_TEMPLATES[module] = f.read()
    return _HTML_TEMPLATES[module].replace("__VERSION__", APP_VERSION)

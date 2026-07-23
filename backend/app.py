"""
BCR Servicios Unificados — orquestador principal.

Cada módulo de negocio vive en su propia carpeta (lluvias/, social/, agenda/,
semana_datos/) y expone un APIRouter. Este archivo solo:
  - Crea la app FastAPI y middlewares.
  - Inicializa la DB.
  - Monta los routers de cada módulo.
  - Sirve los frontends estáticos (con cache-busting).
"""
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from auth import SESSION_TOKEN, require_auth, role_for_password
from config import STATIC_DIR, NoCacheStaticFiles, get_module_html
from database import Base, engine
from migrate import migrate

# Importamos los módulos de modelos para que SQLAlchemy registre las tablas
# antes de create_all (side effect del import).
import agenda_models  # noqa: F401
import bot.db_models  # noqa: F401  — registra BotExchange + BotSession
import conversatorio.models  # noqa: F401  — registra Sugerencia
import capacita.models  # noqa: F401  — registra CapacitaLead
import metricas.models  # noqa: F401  — registra Programa + Instancia
import aapresid.models  # noqa: F401  — registra tablas aap_* (Congreso Aapresid)
import disponibilidad.models  # noqa: F401  — registra tabla disp_responses

# Routers de cada módulo
from agenda.router import router as agenda_api
from bot.router import router as bot_api
from buscador.router import router as buscador_api
from compromisos.router import router as compromisos_api
from conversatorio.router import router as conversatorio_api
from capacita.router import router as capacita_api
from lluvias.router import router as lluvias_api
from metricas.router import router as metricas_api
from social.router import router as social_api
from semana_datos.router import router as semana_datos_api
from aapresid.router import router as aapresid_api
from disponibilidad.router import router as disponibilidad_api


# Crear tablas y ejecutar migraciones (incluido seed de efemérides si la tabla
# está vacía).
Base.metadata.create_all(bind=engine)
migrate()


app = FastAPI(title="BCR Servicios Unificados")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.3.0"}


# ---------------------------------------------------------
# Autenticación (público — POST /api/auth/login; GET /api/auth/check requiere token)
# ---------------------------------------------------------
@app.post("/api/auth/login")
async def auth_login(payload: dict):
    role = role_for_password(payload.get("password"))
    if role:
        # Mismo token para los dos roles (acceso idéntico a la API); el `role`
        # lo usa el frontend para mostrar la UI que corresponde.
        return {"token": SESSION_TOKEN, "role": role}
    raise HTTPException(status_code=401, detail="Contraseña incorrecta")


@app.get("/api/auth/check")
async def auth_check(_: bool = Depends(require_auth)):
    return {"ok": True}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Routers de los módulos
# ---------------------------------------------------------
app.include_router(lluvias_api)
app.include_router(social_api)
app.include_router(agenda_api)
app.include_router(semana_datos_api)
app.include_router(bot_api)
app.include_router(buscador_api)
app.include_router(conversatorio_api)
app.include_router(capacita_api)
app.include_router(metricas_api)
app.include_router(compromisos_api)
app.include_router(aapresid_api)
app.include_router(disponibilidad_api)


# ---------------------------------------------------------
# Scheduler in-process del bot (cron jobs de scrapers BCR).
# Asume un único worker — ver bot/scheduler.py si escalamos.
# ---------------------------------------------------------
from bot.scheduler import start as start_bot_scheduler  # noqa: E402

start_bot_scheduler()


# ---------------------------------------------------------
# Archivos estáticos generados por la app (uploads, mapas, videos).
# Cachean libremente — los nombres incluyen UUIDs/timestamps, son inmutables.
# ---------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------
# Endpoints custom para los frontends — sirven el HTML con __VERSION__
# reemplazado por el commit hash (cache-busting). Cada módulo necesita un
# redirect de /modulo a /modulo/ para que las URLs relativas del HTML se
# resuelvan contra el directorio.
# ---------------------------------------------------------
def _make_html_handlers(module: str):
    """Genera el par (redirect, index) para un módulo dado."""
    async def redirect():
        return RedirectResponse(url=f"/{module}/", status_code=307)

    async def index():
        return HTMLResponse(
            content=get_module_html(module),
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )
    return redirect, index


for _mod in ("lluvias", "social", "agenda", "semana-datos", "bot", "aapresid", "disponibilidad"):
    _redir, _idx = _make_html_handlers(_mod)
    app.get(f"/{_mod}")(_redir)
    app.get(f"/{_mod}/")(_idx)


# ---------------------------------------------------------
# Agenda de Compromisos institucionales (vista pública para autoridades BCR).
# URL: /compromisos/{token}  — el token se valida en el frontend contra el API.
# Servimos el mismo HTML para cualquier token: el JS lee el token del path y
# pega al /api/compromisos/{token} que sí valida y devuelve 404 si no coincide.
# ---------------------------------------------------------
@app.get("/compromisos/{token}")
async def _compromisos_page(token: str):  # noqa: ARG001 — token usado por el JS, no acá
    return HTMLResponse(
        content=get_module_html("compromisos"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# Conversatorio a la carta — dos páginas: form público (/conversatorio/) y
# admin (/conversatorio/admin). No usan __VERSION__ porque todo el CSS/JS
# vive inline en cada HTML, así que vamos directo con FileResponse.
_CONV_DIR = os.path.join(STATIC_DIR, "conversatorio")


@app.get("/conversatorio")
async def _conv_redirect():
    return RedirectResponse(url="/conversatorio/", status_code=307)


@app.get("/conversatorio/")
async def _conv_index():
    return FileResponse(
        os.path.join(_CONV_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/conversatorio/admin")
async def _conv_admin():
    return FileResponse(
        os.path.join(_CONV_DIR, "admin.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# BCR Capacita — formulario público de campaña (/capacita/). CSS/JS en archivos
# separados dentro de la carpeta, así que servimos el index.html con FileResponse.
_CAPACITA_DIR = os.path.join(STATIC_DIR, "capacita")


@app.get("/capacita")
async def _capacita_redirect():
    return RedirectResponse(url="/capacita/", status_code=307)


@app.get("/capacita/")
async def _capacita_index():
    return FileResponse(
        os.path.join(_CAPACITA_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/capacita/admin")
async def _capacita_admin():
    return FileResponse(
        os.path.join(_CAPACITA_DIR, "admin.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# Métricas FBCR — dashboard público (/metricas/) + admin de carga
# (/metricas/admin). CSS/JS inline en cada HTML, así que FileResponse directo.
_METRICAS_DIR = os.path.join(STATIC_DIR, "metricas")


@app.get("/metricas")
async def _metricas_redirect():
    return RedirectResponse(url="/metricas/", status_code=307)


@app.get("/metricas/")
async def _metricas_index():
    return FileResponse(
        os.path.join(_METRICAS_DIR, "index.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/metricas/admin")
async def _metricas_admin():
    return FileResponse(
        os.path.join(_METRICAS_DIR, "admin.html"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# ---------------------------------------------------------
# Frontends estáticos. NoCacheStaticFiles fuerza al browser a revalidar.
# html=False en todos porque los endpoints de arriba sirven el index.html
# con __VERSION__ inyectada.
# ---------------------------------------------------------
app.mount("/lluvias", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "lluvias"), html=False), name="lluvias_ui")
app.mount("/social", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "social"), html=False), name="social_ui")
app.mount("/agenda", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "agenda"), html=False), name="agenda_ui")
app.mount("/semana-datos", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "semana-datos"), html=False), name="semana_datos_ui")
app.mount("/bot", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "bot"), html=False), name="bot_ui")
app.mount("/conversatorio", NoCacheStaticFiles(directory=_CONV_DIR, html=False), name="conversatorio_ui")
app.mount("/capacita", NoCacheStaticFiles(directory=_CAPACITA_DIR, html=False), name="capacita_ui")
app.mount("/metricas", NoCacheStaticFiles(directory=_METRICAS_DIR, html=False), name="metricas_ui")
app.mount("/aapresid", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "aapresid"), html=False), name="aapresid_ui")
app.mount("/disponibilidad", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "disponibilidad"), html=False), name="disponibilidad_ui")


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

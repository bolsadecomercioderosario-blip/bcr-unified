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
from sqlalchemy.orm import Session

from auth import (
    require_auth, role_for_password, token_for_role,
    authenticate_user, create_session, get_actor, hash_password,
    verify_password_hash, seed_users_if_empty, Actor,
)
from config import STATIC_DIR, NoCacheStaticFiles, get_module_html, APP_VERSION
from database import Base, engine, get_db, SessionLocal
from migrate import migrate

# Importamos los módulos de modelos para que SQLAlchemy registre las tablas
# antes de create_all (side effect del import).
import agenda_models  # noqa: F401
import user_models  # noqa: F401  — registra AppUser + UserSession (login por usuario)
import bot.db_models  # noqa: F401  — registra BotExchange + BotSession
import capacita.models  # noqa: F401  — registra CapacitaLead
import metricas.models  # noqa: F401  — registra Programa + Instancia
import noticias.models  # noqa: F401  — registra tabla noticias (sitio Más BCR)
import abuela.models  # noqa: F401  — registra tablas ab_* (panel interno de la murga: caja, ensayos, toques)

# Routers de cada módulo
from agenda.router import router as agenda_api
from bot.router import router as bot_api
from buscador.router import router as buscador_api
from compromisos.router import router as compromisos_api
from capacita.router import router as capacita_api
from lluvias.router import router as lluvias_api
from social.router import router as social_api
from semana_datos.router import router as semana_datos_api
from noticias.router import (
    router as noticias_api, site as noticias_site,
    kit_api as noticias_kit_api, videos_api as noticias_videos_api,
)
from abuela.router import router as abuela_api
from admin.router import router as admin_api  # panel de usuarios (sólo admin)


# Crear tablas y ejecutar migraciones (incluido seed de efemérides si la tabla
# está vacía).
Base.metadata.create_all(bind=engine)
migrate()

# Seed de usuarios individuales (login por email). Sólo actúa la 1ra vez y si
# está seteada USERS_BOOTSTRAP_PASSWORD; si no, no hace nada (el login compartido
# sigue funcionando). No rompe nada existente.
_seed_db = SessionLocal()
try:
    seed_users_if_empty(_seed_db)
finally:
    _seed_db.close()


app = FastAPI(title="BCR Servicios Unificados")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.3.0"}


# ---------------------------------------------------------
# Autenticación (público — POST /api/auth/login; GET /api/auth/check requiere token)
# ---------------------------------------------------------
@app.post("/api/auth/login")
async def auth_login(payload: dict, db: Session = Depends(get_db)):
    # Si viene "email" → login por usuario individual (contraseña propia en DB).
    # Si no → login compartido/área (contraseña por rol, como siempre). Así conviven
    # los dos durante la transición: nadie pierde acceso.
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    if email:
        user = authenticate_user(db, email, password)
        if not user:
            raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
        token = create_session(db, user)
        return {
            "token": token,
            "role": user.role,
            "email": user.email,
            "name": user.name,
            "is_admin": user.is_admin,
            "must_change_password": user.must_change_password,
        }
    role = role_for_password(password)
    if role:
        # Token propio del rol: el backend lo usa para saber quién sos y aplicar
        # permisos; el frontend usa `role` para ajustar la UI.
        return {"token": token_for_role(role), "role": role}
    raise HTTPException(status_code=401, detail="Contraseña incorrecta")


@app.post("/api/auth/change-password")
async def auth_change_password(payload: dict, actor: Actor = Depends(get_actor),
                               db: Session = Depends(get_db)):
    """Cambio de contraseña del usuario logueado (login por email). En el primer
    ingreso (must_change_password) no pide la actual; después sí."""
    if actor.user is None:
        raise HTTPException(status_code=400, detail="El cambio de contraseña es sólo para usuarios individuales.")
    new_password = payload.get("new_password") or ""
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres.")
    user = db.query(user_models.AppUser).filter(user_models.AppUser.id == actor.user.id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.must_change_password:
        # Cambio voluntario (no forzado): exige la contraseña actual.
        if not verify_password_hash(payload.get("current_password") or "", user.password_hash):
            raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta.")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    return {"ok": True}


@app.get("/api/auth/check")
async def auth_check(_: bool = Depends(require_auth)):
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(actor: Actor = Depends(get_actor)):
    """Info del actor logueado (para que el front ajuste la UI: rol, si es usuario,
    admin, si debe cambiar contraseña)."""
    return {
        "role": actor.role,
        "email": actor.email,
        "name": actor.user.name if actor.user else None,
        "is_user": actor.user is not None,
        "is_admin": actor.is_admin,
        "must_change_password": bool(actor.user and actor.user.must_change_password),
    }


# CORS restringido a los dominios propios (antes era "*"). Los frontends de la
# app son same-origin (se sirven del mismo host que la API), así que esto no los
# afecta; sólo evita que sitios de terceros llamen a la API desde el navegador.
ALLOWED_ORIGINS = [
    "https://bcrapps.com",
    "https://www.bcrapps.com",
    "https://bcr-lluvias-app.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Cabeceras de seguridad en todas las respuestas.
# - Anti-clickjacking: ninguna página de la app debe embeberse en sitios de
#   terceros (MásBCR y los paneles incluidos). X-Frame-Options (navegadores
#   viejos) + CSP frame-ancestors 'self' (moderno). 'self' permite que las
#   páginas de la app se embeban entre sí (mismo origen) pero no desde afuera.
#   frame-ancestors NO afecta a que NOSOTROS embebamos a otros (ej. Power BI en
#   el tablero) ni a los scripts/estilos inline.
# - No ponemos una CSP completa (script-src/style-src) porque la app usa mucho
#   inline y la rompería; frame-ancestors es seguro de agregar solo.
@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
    return response


# ---------------------------------------------------------
# Routers de los módulos
# ---------------------------------------------------------
app.include_router(lluvias_api)
app.include_router(social_api)
app.include_router(agenda_api)
app.include_router(semana_datos_api)
app.include_router(bot_api)
app.include_router(buscador_api)
app.include_router(capacita_api)
# metricas_api en stand-by (no se monta la API; ver _metricas_standby).
app.include_router(compromisos_api)
app.include_router(noticias_api)      # API del admin (/api/noticias)
app.include_router(noticias_kit_api)     # API del Kit Multimedia (/api/kit)
app.include_router(noticias_videos_api)  # API de Videos (/api/videos)
app.include_router(noticias_site)        # sitio público server-rendered (/noticias/...)
app.include_router(abuela_api)
app.include_router(admin_api)            # panel de usuarios (/api/admin/*, sólo admin)


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


for _mod in ("lluvias", "social", "agenda", "semana-datos", "abuela"):
    _redir, _idx = _make_html_handlers(_mod)
    app.get(f"/{_mod}")(_redir)
    app.get(f"/{_mod}/")(_idx)


# Bot — página de revisión/aprobación de la coyuntura automática. Protegida por
# auth.js (a diferencia del chat /bot que es público). Se registra antes del
# mount estático de /bot para precedencia. Sirve coyuntura.html (no index.html).
@app.get("/bot/coyuntura")
async def _bot_coyuntura():
    with open(os.path.join(STATIC_DIR, "bot", "coyuntura.html"), encoding="utf-8") as f:
        html = f.read().replace("__VERSION__", APP_VERSION)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, must-revalidate"})


# Noticias (Más BCR) — editor de carga (admin), protegido por auth.js. El sitio
# público (/noticias/, /noticias/nota/{slug}, ...) lo sirve el router server-rendered.
@app.get("/noticias/admin")
async def _noticias_admin():
    with open(os.path.join(STATIC_DIR, "noticias", "admin.html"), encoding="utf-8") as f:
        html = f.read().replace("__VERSION__", APP_VERSION)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, must-revalidate"})


# Kit Multimedia — admin de galerías. En /noticias/kit-admin (NO /noticias/kit/admin
# para no chocar con la ruta pública /noticias/kit/{cat}).
@app.get("/noticias/kit-admin")
async def _noticias_kit_admin():
    with open(os.path.join(STATIC_DIR, "noticias", "kit-admin.html"), encoding="utf-8") as f:
        html = f.read().replace("__VERSION__", APP_VERSION)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/noticias/videos-admin")
async def _noticias_videos_admin():
    with open(os.path.join(STATIC_DIR, "noticias", "videos-admin.html"), encoding="utf-8") as f:
        html = f.read().replace("__VERSION__", APP_VERSION)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, must-revalidate"})


# Panel de administración de usuarios (login por email). Protegido por auth.js +
# require_admin en el backend: aunque alguien abra la página, /api/admin/* le
# devuelve 403 si no es admin. La página misma verifica /api/auth/me y muestra
# "sin permisos" si no corresponde.
def _admin_users_page():
    with open(os.path.join(STATIC_DIR, "admin", "index.html"), encoding="utf-8") as f:
        html = f.read().replace("__VERSION__", APP_VERSION)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/admin")
async def _admin_index():
    return _admin_users_page()


@app.get("/admin/")
async def _admin_index_slash():
    return _admin_users_page()


# ---------------------------------------------------------
# Agenda de Compromisos institucionales (vista pública para autoridades BCR).
# URL: /compromisos/{token}  — el token se valida en el frontend contra el API.
# Servimos el mismo HTML para cualquier token: el JS lee el token del path y
# pega al /api/compromisos/{token} que sí valida y devuelve 404 si no coincide.
# ---------------------------------------------------------
@app.get("/compromisos")
async def _compromisos_page_public():
    return HTMLResponse(
        content=get_module_html("compromisos"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/compromisos/{token}")
async def _compromisos_page(token: str):  # noqa: ARG001 — compat links viejos con token
    return HTMLResponse(
        content=get_module_html("compromisos"),
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


# Métricas FBCR — EN STAND-BY (2026-09). El dashboard y su API se dieron de baja
# a pedido; el código y los datos quedan intactos para reactivarlo cuando pidan.
# Mientras tanto, /metricas y /metricas/admin muestran una pantalla de "no
# disponible" (en vez de 404). Para reactivar: descomentar el include_router y
# el mount, y restaurar los handlers index/admin con FileResponse.
_METRICAS_STANDBY_HTML = (
    "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>Sección no disponible</title>"
    "<style>body{font-family:system-ui,Arial,sans-serif;background:#0f172a;color:#e2e8f0;"
    "display:flex;min-height:100vh;margin:0;align-items:center;justify-content:center;text-align:center;padding:2rem}"
    ".box{max-width:32rem}h1{font-size:1.4rem;margin:0 0 .5rem}p{color:#94a3b8;line-height:1.5}</style></head>"
    "<body><div class='box'><h1>Sección no disponible por el momento</h1>"
    "<p>El tablero de métricas está temporalmente fuera de servicio.</p></div></body></html>"
)


@app.get("/metricas")
@app.get("/metricas/")
@app.get("/metricas/admin")
async def _metricas_standby():
    return HTMLResponse(content=_METRICAS_STANDBY_HTML, status_code=503,
                        headers={"Cache-Control": "no-store"})


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
app.mount("/capacita", NoCacheStaticFiles(directory=_CAPACITA_DIR, html=False), name="capacita_ui")
# /metricas en stand-by: no se monta (ver handler _metricas_standby arriba).
app.mount("/abuela", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "abuela"), html=False), name="abuela_ui")

# Prototipo de la nueva web institucional (HTML estáticos autocontenidos). El hub
# lo abre en /portal/bcr_home_mvp_34.html; las páginas se enlazan entre sí por
# nombre relativo. NoCache para poder iterar el prototipo sin caché del browser.
app.mount("/portal", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "portal"), html=False), name="portal")


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

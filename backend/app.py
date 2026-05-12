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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import STATIC_DIR, NoCacheStaticFiles, get_module_html
from database import Base, engine
from migrate import migrate

# Importamos agenda_models para que SQLAlchemy registre las tablas antes de
# create_all (registra Activity + Efemeride como side effect del import).
import agenda_models  # noqa: F401

# Routers de cada módulo
from agenda.router import router as agenda_api
from lluvias.router import router as lluvias_api
from social.router import router as social_api
from semana_datos.router import router as semana_datos_api


# Crear tablas y ejecutar migraciones (incluido seed de efemérides si la tabla
# está vacía).
Base.metadata.create_all(bind=engine)
migrate()


app = FastAPI(title="BCR Servicios Unificados")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.3.0"}


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


# ---------------------------------------------------------
# Archivos estáticos generados por la app (uploads, mapas, videos).
# Cachean libremente — los nombres incluyen UUIDs/timestamps, son inmutables.
# ---------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------
# Endpoints custom para los frontends que usan cache-busting con __VERSION__.
# El HTML se sirve desde un endpoint propio (no por StaticFiles) para inyectar
# el commit hash. Tienen que redirigir desde /modulo a /modulo/ para que las
# URLs relativas del HTML se resuelvan bien.
# ---------------------------------------------------------
@app.get("/agenda")
async def agenda_redirect():
    return RedirectResponse(url="/agenda/", status_code=307)


@app.get("/agenda/")
async def agenda_index():
    return HTMLResponse(
        content=get_module_html("agenda"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/semana-datos")
async def semana_datos_redirect():
    return RedirectResponse(url="/semana-datos/", status_code=307)


@app.get("/semana-datos/")
async def semana_datos_index():
    return HTMLResponse(
        content=get_module_html("semana-datos"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# ---------------------------------------------------------
# Frontends estáticos. NoCacheStaticFiles fuerza al browser a revalidar.
# Para /agenda y /semana-datos, html=False porque sus endpoints custom sirven
# el index.html con __VERSION__ inyectada. Para /lluvias y /social todavía no
# tienen ese sistema, así que html=True.
# ---------------------------------------------------------
app.mount("/lluvias", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "lluvias"), html=True), name="lluvias_ui")
app.mount("/social", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "social"), html=True), name="social_ui")
app.mount("/agenda", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "agenda"), html=False), name="agenda_ui")
app.mount("/semana-datos", NoCacheStaticFiles(directory=os.path.join(STATIC_DIR, "semana-datos"), html=False), name="semana_datos_ui")


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

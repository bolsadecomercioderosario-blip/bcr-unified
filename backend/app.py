from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse, Response
from pydantic import BaseModel
import os
import shutil
import uuid
from typing import Optional, List
import openai

import requests
from utils.drive import CLIENT_SECRETS_FILE, SCOPES, TOKEN_FILE, create_activity_folder, delete_drive_folder
from google_auth_oauthlib.flow import Flow

# Cloudinary (CDN para imágenes del newsletter). Sólo se activa si las
# tres env vars están presentes; si faltan, los uploads caen al storage
# local — útil para desarrollo y como fallback si el servicio falla.
import cloudinary
import cloudinary.uploader

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

# Imports desde la lógica unificada
from scraper import get_rainfall_metadata, create_animated_video_from_data
from processor import extract_pdf_data, generate_pdf_thumbnail, create_ig_mockup, to_bold_serif

# Base de datos
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import agenda_models
from migrate import migrate

# Crear tablas y ejecutar migraciones
Base.metadata.create_all(bind=engine)
migrate()

app = FastAPI(title="BCR Servicios Unificados")

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.2.0"}

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Definición de rutas base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")

# Asegurar que existan las carpetas necesarias
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Estado global simple para el video de lluvias
video_status = {"ready": False, "error": None, "url": None}


# ---------------------------------------------------------
# CACHE-BUSTING para assets estáticos
# ---------------------------------------------------------
# RENDER_GIT_COMMIT lo expone Render automáticamente; en local cae a 'dev'.
# Truncado a 7 chars para que sea legible.
APP_VERSION = os.environ.get("RENDER_GIT_COMMIT", "dev")[:7]


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles que pide al browser revalidar siempre.
    El browser usa If-Modified-Since y el server responde 304 si no cambió,
    evitando que CSS/JS queden cacheados stale después de un deploy."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


# Cache en memoria de los HTML de cada módulo — se leen una sola vez por proceso
# y se devuelven con __VERSION__ reemplazado por el commit hash de Render.
_HTML_TEMPLATES: dict = {}


def get_module_html(module: str) -> str:
    """Lee y cachea el index.html de un módulo (ej. 'agenda', 'semana-datos').
    Reemplaza __VERSION__ por APP_VERSION para cache-busting de assets."""
    if module not in _HTML_TEMPLATES:
        path = os.path.join(STATIC_DIR, module, "index.html")
        with open(path, "r", encoding="utf-8") as f:
            _HTML_TEMPLATES[module] = f.read()
    return _HTML_TEMPLATES[module].replace("__VERSION__", APP_VERSION)


def get_agenda_html():  # backwards-compat con código existente
    return get_module_html("agenda")

# ---------------------------------------------------------
# LLUVIAS API ROUTER
# ---------------------------------------------------------
lluvias_api = APIRouter(prefix="/api/lluvias")

@lluvias_api.get("/generar_pieza")
async def generar_lluvias(background_tasks: BackgroundTasks):
    top_5, texto, imagen_url, no_lluvias = get_rainfall_metadata()
    
    video_enabled = not no_lluvias
    
    if video_enabled:
        # Guardamos el mapa en la carpeta compartida de uploads
        map_local_path = os.path.join(UPLOADS_DIR, "mapa_lluvias.jpg")
        background_tasks.add_task(video_generation_task, top_5, map_local_path)
    
    return {
        "texto": texto,
        "imagen_url": imagen_url,
        "video_status": "processing" if video_enabled else "disabled",
        "no_lluvias": no_lluvias
    }

@lluvias_api.get("/video_status")
def get_video_status_endpoint():
    if video_status["ready"]:
        return {"status": "ready", "video_url": video_status["url"]}
    if video_status["error"]:
        return {"status": "error", "message": video_status["error"]}
    return {"status": "processing"}

def video_generation_task(top_5, map_path):
    global video_status
    video_status["ready"] = False
    video_status["error"] = None
    try:
        import time
        timestamp = int(time.time())
        filename = f"historia_lluvias_{timestamp}.mp4"
        output_path = os.path.join(UPLOADS_DIR, filename)
        
        # Limpiar videos antiguos
        for f in os.listdir(UPLOADS_DIR):
            if f.startswith("historia_lluvias_") and f.endswith(".mp4"):
                try: os.remove(os.path.join(UPLOADS_DIR, f))
                except: pass
            
        create_animated_video_from_data(top_5, map_path, output_mp4=output_path)
        video_status["url"] = f"/static/uploads/{filename}"
        video_status["ready"] = True
    except Exception as e:
        print(f"Error en tarea de video: {e}")
        video_status["error"] = str(e)

# ---------------------------------------------------------
# SOCIAL API ROUTER
# ---------------------------------------------------------
social_api = APIRouter(prefix="/api/social")

@social_api.post("/pre-procesar")
async def pre_procesar(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    pdf_path = os.path.join(UPLOADS_DIR, f"{session_id}_pre.pdf")
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    try:
        data = extract_pdf_data(pdf_path)
        thumb_filename = f"pre_{session_id}.jpg"
        thumb_path = os.path.join(UPLOADS_DIR, thumb_filename)
        generate_pdf_thumbnail(pdf_path, thumb_path)
        
        return {
            "session_id": session_id, 
            "title": data["title"], 
            "pdf_path": pdf_path,
            "preview_url": f"/static/uploads/{thumb_filename}"
        }
    except Exception as e:
        return {"error": str(e)}

@social_api.post("/generar")
async def generar_social(
    session_id: str = Form(...),
    pdf_path: str = Form(...),
    title: str = Form(...)
):
    try:
        data = extract_pdf_data(pdf_path)
        data["title"] = title
        
        twitter_text = f"{to_bold_serif(data['title'])}\n\n{data['intro']}"
        
        thumb_filename = f"comunicado_{session_id}.jpg"
        thumb_path = os.path.join(UPLOADS_DIR, thumb_filename)
        generate_pdf_thumbnail(pdf_path, thumb_path)
        
        story_filename = f"story_instagram_{session_id}.jpg"
        story_path = os.path.join(UPLOADS_DIR, story_filename)
        create_ig_mockup(data, thumb_path, ASSETS_DIR, story_path)
        
        return {
            "twitter_text": twitter_text,
            "comunicado_url": f"/api/social/descargar/{thumb_filename}?name=comunicado.jpg",
            "story_url": f"/api/social/descargar/{story_filename}?name=story_instagram.jpg",
            "comunicado_img": f"/static/uploads/{thumb_filename}",
            "story_img": f"/static/uploads/{story_filename}"
        }
    except Exception as e:
        return {"error": str(e)}

@social_api.get("/descargar/{filename}")
async def descargar(filename: str, name: str):
    file_path = os.path.join(UPLOADS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename=name, media_type='image/jpeg')
    return {"error": "Archivo no encontrado"}

# ---------------------------------------------------------
# AGENDA API ROUTER
# ---------------------------------------------------------
agenda_api = APIRouter(prefix="/api/agenda")

@agenda_api.post("/generate-copy")
def generate_copy(request: agenda_models.GenerateCopyRequest):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY no está configurada en el servidor.")
        
    client = openai.OpenAI(api_key=api_key)
    
    if request.mode == 'ig':
        system_prompt = """Sos redactor institucional de la Bolsa de Comercio de Rosario.
Tu tarea es redactar un copy para Instagram Stories a partir de la información disponible de una actividad.

⚠️ REGLAS CLAVE
Usar únicamente la información disponible
No inventar datos ni agregar información no proporcionada
Si hay poca información, mantener el texto general y breve
Integrar los campos de forma natural, sin asumir jerarquías entre ellos
No escribas la palabra 'Título:' ni uses prefijos, simplemente redactá el texto del título.

📐 FORMATO DE SALIDA
Generar siempre:
Un título
Un primer párrafo
Un segundo párrafo
No incluir etiquetas ni explicaciones. El texto debe estar listo para publicar.

✍️ ESTILO
Redacción en pasado
Tono institucional, claro y sobrio
Lenguaje profesional y accesible
Evitar adjetivos innecesarios o grandilocuentes
No usar emojis
No usar citas textuales

🧩 CONSTRUCCIÓN
Título: Claro y descriptivo.
Primer párrafo: Explicar qué ocurrió. Incluir a la Bolsa de Comercio de Rosario como protagonista.
Segundo párrafo: Explicar el sentido del encuentro, temas abordados o marco institucional. Si no hay detalles suficientes, usar formulaciones generales institucionales (por ejemplo: fortalecimiento de vínculos, agenda de trabajo, articulación, intercambio)."""
    elif request.mode == 'li':
        system_prompt = """Sos redactor institucional de la Bolsa de Comercio de Rosario.
Tu tarea es redactar un copy para LinkedIn o el newsletter Conectados a partir de la información disponible de una actividad.

⚠️ REGLAS CLAVE
Usar únicamente la información disponible. No inventar datos ni cargos.
ESCALA Y ESTRUCTURA:
1. TÍTULO: Un título claro, formal y descriptivo al inicio (ej. "Primera Jornada de la Mesa de Legumbres de Santa Fe").
2. PRIMER PÁRRAFO: Arrancar mencionando a la Bolsa de Comercio de Rosario como sede o protagonista, explicando de qué trata el encuentro. (ej. "La Bolsa de Comercio de Rosario fue sede de... un espacio de encuentro orientado a...").
3. SEGUNDO PÁRRAFO: Desarrollar quiénes participaron (ej. referentes del ámbito público, privado y académico) y los temas tratados (producción, innovación, mercados, etc.) promoviendo el desarrollo del sector.
4. PÁRRAFO FINAL (Autoridades): Si se envían nombres en "Autoridades Presentes", agregarlos SIEMPRE al final en un párrafo separado, con redacción estrictamente sobria y enumerativa: "Por la BCR, participaron...".

✍️ ESTILO
Redacción en pasado.
Tono institucional, profesional, narrativo y descriptivo.
No usar emojis ni adjetivos grandilocuentes.
No usar etiquetas ni explicaciones en tu respuesta, entregar el texto final directamente."""
    else:
        raise HTTPException(status_code=400, detail="Modo inválido. Use 'ig' o 'li'.")

    user_content = f"Título: {request.title}\nDescripción: {request.description}\nObservaciones: {request.observations}"
    if request.mode == 'li' and request.participants_enriched:
        user_content += f"\nAutoridades Presentes (Agregar al final como se indicó): {request.participants_enriched}"
        
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3
        )
        return {"copy": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@agenda_api.post("/upload")
async def upload_agenda_image(file: UploadFile = File(...)):
    # 1) Intento primario: Cloudinary (CDN). El email enviado por el CRM va a
    #    pedir las imágenes desde res.cloudinary.com — estable y rápido.
    if CLOUDINARY_ENABLED:
        try:
            result = cloudinary.uploader.upload(
                file.file,
                folder="bcr-newsletter",
                resource_type="image",
            )
            secure_url = result.get("secure_url")
            if secure_url:
                return {"url": secure_url}
            # Si el SDK no devolvió secure_url, registramos y caemos al fallback.
            print(f"Cloudinary no devolvió secure_url. Respuesta: {result}")
        except Exception as e:
            print(f"Error subiendo a Cloudinary, fallback a local: {e}")
            # Rebobinar el stream para poder leerlo de nuevo desde el fallback.
            try:
                file.file.seek(0)
            except Exception:
                pass

    # 2) Fallback: storage local (UPLOADS_DIR es absoluto, no depende del CWD).
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"newsletter_{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOADS_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/static/uploads/{filename}"}

@agenda_api.post("/auth")
def authenticate_agenda(payload: dict):
    password = payload.get("password")
    # Password por defecto si no se configura en Render
    correct_password = os.getenv("AGENDA_PASSWORD", "bcr2024")
    if password == correct_password:
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Contraseña incorrecta")

def trigger_santiago_webhook(activity_id, title, date, drive_santiago):
    """
    Envía una notificación a Pipedream si hay un link de Santiago.
    Se ejecuta en segundo plano para no bloquear la respuesta.
    """
    webhook_url = os.getenv("SANTIAGO_WEBHOOK_URL")
    if not webhook_url or not drive_santiago:
        return
        
    payload = {
        "event": "santiago_link_ready",
        "activity_id": activity_id,
        "title": title,
        "date": date,
        "drive_santiago": drive_santiago,
        "timestamp": os.getenv("RENDER_GIT_COMMIT", "manual") # Opcional: para tracking
    }
    
    try:
        requests.post(webhook_url, json=payload, timeout=5)
        print(f"Webhook de Santiago disparado para: {title}")
    except Exception as e:
        print(f"Error al disparar webhook de Santiago: {e}")

@agenda_api.get("/actividades", response_model=List[agenda_models.ActivityOut])
def read_activities(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    activities = db.query(agenda_models.Activity).offset(skip).limit(limit).all()
    return activities

@agenda_api.post("/actividades", response_model=agenda_models.ActivityOut)
def create_activity(activity: agenda_models.ActivityCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_activity = agenda_models.Activity(**activity.model_dump())

    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)

    return db_activity

@agenda_api.put("/actividades/{activity_id}", response_model=agenda_models.ActivityOut)
def update_activity(activity_id: str, activity: agenda_models.ActivityUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    old_santiago = db_activity.drive_santiago
    update_data = activity.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_activity, key, value)
        
    db.commit()
    db.refresh(db_activity)
        
    return db_activity

@agenda_api.post("/actividades/{activity_id}/notify-santiago")
def notify_santiago(activity_id: str, payload: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
        
    link = payload.get("drive_santiago")
    if not link:
        raise HTTPException(status_code=400, detail="No se proporcionó el link de Santiago")
        
    # Actualizar el link en la base de datos por si no se guardó antes
    db_activity.drive_santiago = link
    db.commit()
    db.refresh(db_activity)
        
    background_tasks.add_task(
        trigger_santiago_webhook, 
        db_activity.id, db_activity.title, db_activity.date, db_activity.drive_santiago
    )
    return {"ok": True}

@agenda_api.post("/actividades/{activity_id}/create-folder")
def manual_create_folder(activity_id: str, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
        
    if db_activity.drive_bcr:
        return {"link": db_activity.drive_bcr, "already_existed": True}
        
    link = create_activity_folder(db_activity.date, db_activity.title)
    if link:
        db_activity.drive_bcr = link
        db.commit()
        db.refresh(db_activity)
        return {"link": link, "ok": True}
    else:
        raise HTTPException(status_code=500, detail="No se pudo crear la carpeta en Google Drive")

@agenda_api.delete("/actividades/{activity_id}")
def delete_activity(activity_id: str, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    # Si tiene carpeta en Drive, intentar borrarla
    if db_activity.drive_bcr:
        delete_drive_folder(db_activity.drive_bcr)
    if db_activity.drive_santiago:
        delete_drive_folder(db_activity.drive_santiago)
        
    db.delete(db_activity)
    db.commit()
    return {"ok": True}

# ---------------------------------------------------------
# EFEMÉRIDES Y ANIVERSARIOS
# ---------------------------------------------------------
@agenda_api.get("/efemerides", response_model=List[agenda_models.EfemerideOut])
def list_efemerides(db: Session = Depends(get_db)):
    return db.query(agenda_models.Efemeride).order_by(
        agenda_models.Efemeride.mes, agenda_models.Efemeride.dia
    ).all()


@agenda_api.post("/efemerides", response_model=agenda_models.EfemerideOut)
def create_efemeride(payload: agenda_models.EfemerideCreate, db: Session = Depends(get_db)):
    db_ef = agenda_models.Efemeride(**payload.model_dump())
    db.add(db_ef)
    db.commit()
    db.refresh(db_ef)
    return db_ef


@agenda_api.put("/efemerides/{ef_id}", response_model=agenda_models.EfemerideOut)
def update_efemeride(ef_id: int, payload: agenda_models.EfemerideUpdate, db: Session = Depends(get_db)):
    db_ef = db.query(agenda_models.Efemeride).filter(agenda_models.Efemeride.id == ef_id).first()
    if not db_ef:
        raise HTTPException(status_code=404, detail="Efeméride no encontrada")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_ef, key, value)
    db.commit()
    db.refresh(db_ef)
    return db_ef


@agenda_api.delete("/efemerides/{ef_id}")
def delete_efemeride(ef_id: int, db: Session = Depends(get_db)):
    db_ef = db.query(agenda_models.Efemeride).filter(agenda_models.Efemeride.id == ef_id).first()
    if not db_ef:
        raise HTTPException(status_code=404, detail="Efeméride no encontrada")
    db.delete(db_ef)
    db.commit()
    return {"ok": True}


oauth_state_store = {}

@agenda_api.get("/drive/auth")
def drive_auth():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return {"error": "client_secret.json no encontrado en el servidor."}
        
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = 'http://localhost:8000/api/agenda/drive/callback'
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Guardamos temporalmente el verificador en memoria (necesario para OAuth)
    if hasattr(flow, 'code_verifier'):
        oauth_state_store[state] = flow.code_verifier
        
    return RedirectResponse(url=authorization_url)

@agenda_api.get("/drive/callback")
def drive_callback(code: str, state: str = None):
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return {"error": "client_secret.json no encontrado"}
        
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = 'http://localhost:8000/api/agenda/drive/callback'
    
    # Restauramos el verificador
    if state and state in oauth_state_store:
        flow.code_verifier = oauth_state_store.pop(state)
        
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())
        
    return {"message": "✅ Autenticación exitosa. Se guardó token.json en el servidor. Ya podés cerrar esta pestaña."}

# ---------------------------------------------------------
# SEMANA EN DATOS — publicación del programa semanal (M1: preview)
# ---------------------------------------------------------
from utils.informes import fetch_informe, InformeNotFound
from utils.semana_datos import generate_portada_yt, generate_portada_reel, build_title, build_description
from utils.youtube_upload import (
    extract_drive_file_id,
    get_drive_file_metadata,
    upload_program_to_youtube,
    SEMANA_DATOS_PLAYLIST_ID,
)

semana_datos_api = APIRouter(prefix="/api/semana-datos")


class ScrapeRequest(BaseModel):
    urls: List[str]


class PreviewRequest(BaseModel):
    titulos: List[str]
    copetes: List[str] = []


@semana_datos_api.post("/scrape")
def scrape_informes(req: ScrapeRequest):
    """Scrapea 1 o 2 URLs de informes y devuelve título + copete de cada uno."""
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


@semana_datos_api.post("/preview-portada")
def preview_portada(req: PreviewRequest):
    """Genera la portada de YouTube (PNG) con los títulos dados."""
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


@semana_datos_api.post("/preview-portada-reel")
def preview_portada_reel(req: ReelRequest):
    """Genera UNA portada vertical (Reel/Story) para un informe. Se llama una
    vez por informe (frontend hace 1 o 2 requests según cuántos haya)."""
    titulo = (req.titulo or "").strip()
    if not titulo:
        raise HTTPException(status_code=400, detail="Falta el título")
    try:
        png = generate_portada_reel(titulo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar portada Reel: {e}")
    return Response(content=png, media_type="image/png")


@semana_datos_api.post("/preview-metadata")
def preview_metadata(req: PreviewRequest):
    """Devuelve título y descripción finales (lo que iría como metadata a YouTube)."""
    return {
        "titulo": build_title(req.titulos),
        "descripcion": build_description(req.copetes),
    }


class DriveCheckRequest(BaseModel):
    drive_url: str


@semana_datos_api.post("/drive-check")
def drive_check(req: DriveCheckRequest):
    """Valida que la URL/ID de Drive sea legible por la app y que el archivo
    sea un video. Útil para el frontend antes de disparar el upload."""
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


class UploadRequest(BaseModel):
    drive_url: str
    titulos_portada: List[str]  # títulos para la portada (pueden estar editados)
    titulo_youtube: str           # título para el video
    descripcion: str              # descripción completa


@semana_datos_api.post("/upload-youtube")
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

    # Generamos la portada AL MOMENTO del upload con los títulos actuales
    # (no confiamos en el estado del frontend — el server es la fuente de verdad).
    try:
        portada_png = generate_portada_yt(titulos_portada)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar la portada: {e}")

    # Upload — esto puede demorar varios minutos (descarga + upload).
    # Sincrónico por ahora; en una mejora futura podríamos hacerlo en background
    # con un job ID + polling de estado.
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


class EditClipRequest(BaseModel):
    drive_url: str


# Job tracking en memoria para la edición de recortes.
# Si el proceso de Render reinicia, los jobs se pierden — aceptable para una
# tarea on-demand que se dispara desde el frontend y se pollea de inmediato.
import threading
import time as _time

_clip_jobs: dict = {}


def _run_edit_clip(job_id: str, drive_url: str):
    """Procesa el recorte en background. Actualiza _clip_jobs[job_id]."""
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
            "finished_at": _time.time(),
        })
    except Exception as e:
        import traceback
        print(f"[edit-clip job={job_id}] ERROR: {e}\n{traceback.format_exc()}")
        job.update({
            "status": "error",
            "error": str(e),
            "finished_at": _time.time(),
        })
    finally:
        if input_path:
            try:
                os.remove(input_path)
            except Exception:
                pass


def _gc_old_jobs(ttl_seconds: int = 3600):
    """Borra entradas viejas para no acumular memoria."""
    cutoff = _time.time() - ttl_seconds
    for jid in list(_clip_jobs.keys()):
        started = _clip_jobs[jid].get("started_at", 0)
        if started and started < cutoff:
            _clip_jobs.pop(jid, None)


@semana_datos_api.post("/edit-clip")
def edit_clip_endpoint(req: EditClipRequest):
    """Arranca el procesamiento del recorte en background y devuelve un job_id.
    El cliente debe hacer polling a /edit-clip/status/{job_id} para conocer el resultado.
    """
    _gc_old_jobs()
    job_id = uuid.uuid4().hex
    _clip_jobs[job_id] = {
        "status": "processing",
        "stage": "Iniciando…",
        "started_at": _time.time(),
    }
    t = threading.Thread(target=_run_edit_clip, args=(job_id, req.drive_url), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "processing"}


@semana_datos_api.get("/edit-clip/status/{job_id}")
def edit_clip_status(job_id: str):
    """Devuelve el estado del job. Mientras processing, incluye el stage actual."""
    job = _clip_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado o expirado")
    return job


# ---------------------------------------------------------
# MONTAJE Y RUTAS ESTÁTICAS
# ---------------------------------------------------------
app.include_router(lluvias_api)
app.include_router(social_api)
app.include_router(agenda_api)
app.include_router(semana_datos_api)

# Archivos estáticos generados por la app (uploads, mapas, videos).
# Pueden cachearse libremente — los nombres incluyen UUIDs/timestamps, son inmutables.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Endpoint custom para Agenda: inyecta la versión en los <link>/<script> para
# que el browser fetchee el JS/CSS nuevo después de cada deploy.
# IMPORTANTE: el HTML usa paths relativos (css/style.css), por lo que la URL
# debe terminar en "/" para que el browser los resuelva contra /agenda/. Si el
# usuario llega a /agenda sin slash, redirigimos para que /agenda/ sirva el HTML.
@app.get("/agenda")
async def agenda_redirect():
    return RedirectResponse(url="/agenda/", status_code=307)

@app.get("/agenda/")
async def agenda_index():
    return HTMLResponse(
        content=get_agenda_html(),
        headers={"Cache-Control": "no-cache, must-revalidate"}
    )

# Semana en Datos — mismo patrón: endpoint custom para inyectar versión + mount sin html.
@app.get("/semana-datos")
async def semana_datos_redirect():
    return RedirectResponse(url="/semana-datos/", status_code=307)

@app.get("/semana-datos/")
async def semana_datos_index():
    return HTMLResponse(
        content=get_module_html("semana-datos"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )

# Frontends. NoCacheStaticFiles fuerza al browser a revalidar (304 si no cambió).
# Para /agenda y /semana-datos, html=False porque sus endpoints custom sirven el index.
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

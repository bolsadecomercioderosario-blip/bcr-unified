from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import os
import shutil
import uuid
from typing import Optional, List
import openai

import requests
from utils.drive import CLIENT_SECRETS_FILE, SCOPES, TOKEN_FILE, create_activity_folder, delete_drive_folder
from google_auth_oauthlib.flow import Flow

# Imports desde la lógica unificada
from scraper import get_rainfall_metadata, create_animated_video_from_data
from processor import extract_pdf_data, generate_pdf_thumbnail, create_ig_mockup, to_bold_serif

# Base de datos
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import agenda_models

# Crear tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(title="BCR Servicios Unificados")

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
def notify_santiago(activity_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
        
    if not db_activity.drive_santiago:
        raise HTTPException(status_code=400, detail="No hay link de Santiago configurado")
        
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
# MONTAJE Y RUTAS ESTÁTICAS
# ---------------------------------------------------------
app.include_router(lluvias_api)
app.include_router(social_api)
app.include_router(agenda_api)

# Archivos estáticos (Mapas, videos generados)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Frontends (Cada uno en su subruta)
app.mount("/lluvias", StaticFiles(directory=os.path.join(STATIC_DIR, "lluvias"), html=True), name="lluvias_ui")
app.mount("/social", StaticFiles(directory=os.path.join(STATIC_DIR, "social"), html=True), name="social_ui")
app.mount("/agenda", StaticFiles(directory=os.path.join(STATIC_DIR, "agenda"), html=True), name="agenda_ui")

@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

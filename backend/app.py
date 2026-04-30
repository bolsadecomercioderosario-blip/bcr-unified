from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import os
import shutil
import uuid
from typing import Optional, List
import openai

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
    top_5, texto, imagen_url = get_rainfall_metadata()
    # Guardamos el mapa en la carpeta compartida de uploads
    map_local_path = os.path.join(UPLOADS_DIR, "mapa_lluvias.jpg")
    background_tasks.add_task(video_generation_task, top_5, map_local_path)
    return {
        "texto": texto,
        "imagen_url": imagen_url,
        "video_status": "processing"
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
Tu tarea es redactar un copy para LinkedIn a partir de la información disponible de una actividad.

⚠️ REGLAS CLAVE
Usar únicamente la información disponible.
No inventar datos, cargos, ni agregar información no proporcionada.
Si se envían nombres de personas ("Presentes"), DEBES mencionarlos explícitamente en el texto, respetando sus cargos tal como se te envían. No alteres ni inventes cargos.

📐 FORMATO DE SALIDA
No incluir etiquetas ni explicaciones. El texto debe estar listo para publicar en LinkedIn.
Estructura sugerida: Título institucional, párrafo de contexto de la actividad, mención de los presentes y cierre institucional.

✍️ ESTILO
Redacción en pasado.
Tono institucional, profesional, enfocado en el fortalecimiento institucional.
Evitar adjetivos innecesarios o grandilocuentes.
No usar emojis."""
    else:
        raise HTTPException(status_code=400, detail="Modo inválido. Use 'ig' o 'li'.")

    user_content = f"Título: {request.title}\nDescripción: {request.description}\nObservaciones: {request.observations}"
    if request.mode == 'li' and request.participants_enriched:
        user_content += f"\nPresentes (Integrarlos al texto de forma natural con sus cargos): {request.participants_enriched}"
        
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

@agenda_api.get("/actividades", response_model=List[agenda_models.ActivityOut])
def read_activities(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    activities = db.query(agenda_models.Activity).offset(skip).limit(limit).all()
    return activities

@agenda_api.post("/actividades", response_model=agenda_models.ActivityOut)
def create_activity(activity: agenda_models.ActivityCreate, db: Session = Depends(get_db)):
    db_activity = agenda_models.Activity(**activity.model_dump())
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return db_activity

@agenda_api.put("/actividades/{activity_id}", response_model=agenda_models.ActivityOut)
def update_activity(activity_id: str, activity: agenda_models.ActivityUpdate, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    update_data = activity.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_activity, key, value)
        
    db.commit()
    db.refresh(db_activity)
    return db_activity

@agenda_api.delete("/actividades/{activity_id}")
def delete_activity(activity_id: str, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(db_activity)
    db.commit()
    return {"ok": True}

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

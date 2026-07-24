"""
Módulo Agenda: CRUD de actividades + generación de copy IA + integración
con Drive (carpetas y OAuth) + webhook Santiago + CRUD de Efemérides.
"""
import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

import cloudinary
import cloudinary.uploader
import openai
import requests
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

import agenda_models
from auth import require_auth
from common import require_external_integrations, require_google_drive
from config import CLOUDINARY_ENABLED, UPLOADS_DIR
from database import get_db
from utils.drive import (
    CLIENT_SECRETS_FILE, SCOPES, TOKEN_FILE,
    create_activity_folder, trash_drive_folder,
)


router = APIRouter(prefix="/api/agenda", dependencies=[Depends(require_auth)])


# ---------------------------------------------------------
# Copy con IA (Instagram / LinkedIn)
# ---------------------------------------------------------
@router.post("/generate-copy")
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
    elif request.mode == 'newsletter_block':
        # Modo del botón IA en cada bloque de Conectados.
        # Toma un base_text (LinkedIn, Instagram o info básica) y lo reformula
        # en tono periodístico, devolviendo título + cuerpo separados como JSON.
        system_prompt = """Sos editor periodístico institucional de la Bolsa de Comercio de Rosario.
Te pasan un texto base sobre una actividad de la BCR y tu tarea es reescribirlo
para una sección de newsletter institucional ("Conectados") en tono periodístico
sobrio, informativo y descriptivo.

⚠️ REGLAS
- Usar SÓLO la información del texto base. No inventar nombres, lugares, cargos
  ni datos.
- Redacción en pasado, voz institucional, tercera persona.
- Sin emojis, sin adjetivos grandilocuentes, sin frases publicitarias.
- 2 a 3 párrafos cortos en total. Que sea apto para newsletter — entrada
  rápida, no extenso.

📐 SALIDA — DEVOLVÉ EXACTAMENTE UN JSON CON DOS CAMPOS:
{
  "title": "...",   // Titular periodístico breve (máximo 10 palabras)
  "copy": "..."     // Cuerpo del bloque, 2-3 párrafos separados por \\n\\n
}

No agregues nada fuera del JSON. No uses prefijos como "Título:" en el title."""
    else:
        raise HTTPException(status_code=400, detail="Modo inválido. Use 'ig', 'li' o 'newsletter_block'.")

    if request.mode == 'newsletter_block':
        source_label = {
            'linkedin': 'Copy de LinkedIn ya redactado (úsalo como base principal):',
            'instagram': 'Copy de Instagram ya redactado (úsalo como base principal):',
            'basic': 'Información cruda de la actividad (título, descripción, lugar):',
        }.get(request.base_source or 'basic', 'Texto base:')
        user_content = f"{source_label}\n\n{request.base_text or ''}\n\nTítulo original: {request.title}"
    else:
        user_content = f"Título: {request.title}\nDescripción: {request.description}\nObservaciones: {request.observations}"
        if request.mode == 'li' and request.participants_enriched:
            user_content += f"\nAutoridades Presentes (Agregar al final como se indicó): {request.participants_enriched}"

    try:
        kwargs = dict(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        if request.mode == 'newsletter_block':
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content

        if request.mode == 'newsletter_block':
            import json
            parsed = json.loads(content)
            return {
                "title": (parsed.get("title") or "").strip(),
                "copy": (parsed.get("copy") or "").strip(),
            }
        return {"copy": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# Upload de imágenes del newsletter Conectados (Cloudinary + fallback local)
# ---------------------------------------------------------
@router.post("/upload")
async def upload_agenda_image(file: UploadFile = File(...)):
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
            print(f"Cloudinary no devolvió secure_url. Respuesta: {result}")
        except Exception as e:
            print(f"Error subiendo a Cloudinary, fallback a local: {e}")
            try:
                file.file.seek(0)
            except Exception:
                pass

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"newsletter_{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOADS_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/static/uploads/{filename}"}


# ---------------------------------------------------------
# Upload de archivos adjuntos de la Agenda de Compromisos (DOC/DOCX/PDF/JPG/PNG).
# Lo usa Secretaría desde el form. A diferencia de /upload (sólo imágenes del
# newsletter), acepta documentos: Cloudinary con resource_type="auto" preserva
# el original (raw para .docx, etc.). Devuelve {url, name} — el name es el
# nombre de archivo original, para mostrarlo y descargarlo prolijo.
# ---------------------------------------------------------
_ALLOWED_ATTACHMENT_EXT = {".doc", ".docx", ".pdf", ".jpg", ".jpeg", ".png"}


@router.post("/upload-file")
async def upload_agenda_file(file: UploadFile = File(...)):
    original_name = file.filename or "adjunto"
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in _ALLOWED_ATTACHMENT_EXT:
        raise HTTPException(
            status_code=400,
            detail="Formato no permitido. Subí DOC, DOCX, PDF, JPG o PNG.",
        )

    if CLOUDINARY_ENABLED:
        try:
            result = cloudinary.uploader.upload(
                file.file,
                folder="bcr-agenda-adjuntos",
                resource_type="auto",  # imágenes -> image, docs -> raw
                use_filename=True,
                unique_filename=True,
            )
            secure_url = result.get("secure_url")
            if secure_url:
                return {"url": secure_url, "name": original_name}
            print(f"Cloudinary no devolvió secure_url (adjunto). Respuesta: {result}")
        except Exception as e:
            print(f"Error subiendo adjunto a Cloudinary, fallback a local: {e}")
            try:
                file.file.seek(0)
            except Exception:
                pass

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    filename = f"adjunto_{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOADS_DIR, filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/static/uploads/{filename}", "name": original_name}


# ---------------------------------------------------------
# Webhook Santiago: avisa via Pipedream cuando hay link de Drive listo
# ---------------------------------------------------------
def _trigger_santiago_webhook(activity_id, title, date, drive_santiago):
    webhook_url = os.getenv("SANTIAGO_WEBHOOK_URL")
    if not webhook_url or not drive_santiago:
        return

    payload = {
        "event": "santiago_link_ready",
        "activity_id": activity_id,
        "title": title,
        "date": date,
        "drive_santiago": drive_santiago,
        "timestamp": os.getenv("RENDER_GIT_COMMIT", "manual"),
    }

    try:
        requests.post(webhook_url, json=payload, timeout=5)
        print(f"Webhook de Santiago disparado para: {title}")
    except Exception as e:
        print(f"Error al disparar webhook de Santiago: {e}")


# ---------------------------------------------------------
# CRUD de Actividades
# ---------------------------------------------------------
@router.get("/actividades", response_model=List[agenda_models.ActivityOut])
def read_activities(skip: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    return db.query(agenda_models.Activity).offset(skip).limit(limit).all()


@router.post("/actividades", response_model=agenda_models.ActivityOut)
def create_activity(activity: agenda_models.ActivityCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_activity = agenda_models.Activity(**activity.model_dump())
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return db_activity


@router.put("/actividades/{activity_id}", response_model=agenda_models.ActivityOut)
def update_activity(activity_id: str, activity: agenda_models.ActivityUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    update_data = activity.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_activity, key, value)

    db.commit()
    db.refresh(db_activity)
    return db_activity


@router.post("/actividades/{activity_id}/notify-santiago")
def notify_santiago(activity_id: str, payload: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    require_external_integrations()
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    link = payload.get("drive_santiago")
    if not link:
        raise HTTPException(status_code=400, detail="No se proporcionó el link de Santiago")

    db_activity.drive_santiago = link
    db.commit()
    db.refresh(db_activity)

    background_tasks.add_task(
        _trigger_santiago_webhook,
        db_activity.id, db_activity.title, db_activity.date, db_activity.drive_santiago,
    )
    return {"ok": True}


@router.post("/actividades/{activity_id}/create-folder")
def manual_create_folder(activity_id: str, db: Session = Depends(get_db)):
    require_google_drive()
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
    raise HTTPException(
        status_code=503,
        detail=(
            "No se pudo crear la carpeta: Google Drive no está autorizado o el "
            "token venció. Hay que reautorizar el acceso (scripts/reauth_google.py) "
            "y subir el token.json actualizado al servidor."
        ),
    )


@router.delete("/actividades/{activity_id}")
def delete_activity(activity_id: str, db: Session = Depends(get_db)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if db_activity.drive_bcr:
        trash_drive_folder(db_activity.drive_bcr)
    if db_activity.drive_santiago:
        trash_drive_folder(db_activity.drive_santiago)

    db.delete(db_activity)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# CRUD de Efemérides
# ---------------------------------------------------------
@router.get("/efemerides", response_model=List[agenda_models.EfemerideOut])
def list_efemerides(db: Session = Depends(get_db)):
    return db.query(agenda_models.Efemeride).order_by(
        agenda_models.Efemeride.mes, agenda_models.Efemeride.dia,
    ).all()


@router.post("/efemerides", response_model=agenda_models.EfemerideOut)
def create_efemeride(payload: agenda_models.EfemerideCreate, db: Session = Depends(get_db)):
    db_ef = agenda_models.Efemeride(**payload.model_dump())
    db.add(db_ef)
    db.commit()
    db.refresh(db_ef)
    return db_ef


@router.put("/efemerides/{ef_id}", response_model=agenda_models.EfemerideOut)
def update_efemeride(ef_id: int, payload: agenda_models.EfemerideUpdate, db: Session = Depends(get_db)):
    db_ef = db.query(agenda_models.Efemeride).filter(agenda_models.Efemeride.id == ef_id).first()
    if not db_ef:
        raise HTTPException(status_code=404, detail="Efeméride no encontrada")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(db_ef, key, value)
    db.commit()
    db.refresh(db_ef)
    return db_ef


@router.delete("/efemerides/{ef_id}")
def delete_efemeride(ef_id: int, db: Session = Depends(get_db)):
    db_ef = db.query(agenda_models.Efemeride).filter(agenda_models.Efemeride.id == ef_id).first()
    if not db_ef:
        raise HTTPException(status_code=404, detail="Efeméride no encontrada")
    db.delete(db_ef)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# OAuth de Google Drive (flujo de autenticación)
# ---------------------------------------------------------
_oauth_state_store: dict = {}


def _oauth_redirect_uri() -> str:
    """En producción se setea OAUTH_REDIRECT_URI con la URL de Render; en dev
    cae al localhost histórico. Cualquier URI usado tiene que estar registrado
    en Google Cloud Console → Credentials."""
    return os.environ.get(
        "OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/agenda/drive/callback",
    )


@router.get("/drive/auth")
def drive_auth():
    require_google_drive()
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return {"error": "client_secret.json no encontrado en el servidor."}

    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = _oauth_redirect_uri()

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )

    if hasattr(flow, 'code_verifier'):
        _oauth_state_store[state] = flow.code_verifier

    return RedirectResponse(url=authorization_url)


@router.get("/drive/callback")
def drive_callback(code: str, state: str = None):
    require_google_drive()
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return {"error": "client_secret.json no encontrado"}

    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
    flow.redirect_uri = _oauth_redirect_uri()

    if state and state in _oauth_state_store:
        flow.code_verifier = _oauth_state_store.pop(state)

    flow.fetch_token(code=code)
    creds = flow.credentials

    with open(TOKEN_FILE, 'w') as token:
        token.write(creds.to_json())

    return {"message": "✅ Autenticación exitosa. Se guardó token.json en el servidor. Ya podés cerrar esta pestaña."}


# ---------------------------------------------------------
# Newsletter Conectados — "edición actual" (singleton global)
# Define el rango temporal [start, end] que enmarca la edición que se está
# armando. Frontend lo usa para filtrar qué actividades aparecen en Conectados.
# ---------------------------------------------------------
def _default_edition_range() -> dict:
    """Sábado pasado 00:00 → viernes próximo 23:59 (semana newsletter clásica).
    Se devuelve cuando no hay ningún registro guardado todavía."""
    from datetime import datetime, timedelta
    today = datetime.now()
    # Semana newsletter: sábado a viernes. dow: lun=0..dom=6, sáb=5.
    days_since_saturday = (today.weekday() - 5) % 7
    saturday = (today - timedelta(days=days_since_saturday)).replace(hour=0, minute=0, second=0, microsecond=0)
    friday = (saturday + timedelta(days=6)).replace(hour=23, minute=59)
    return {
        "edition_start_at": saturday.strftime("%Y-%m-%dT%H:%M"),
        "edition_end_at": friday.strftime("%Y-%m-%dT%H:%M"),
    }


@router.get("/newsletter-settings")
def get_newsletter_settings(db: Session = Depends(get_db)):
    """Devuelve la edición actual del Conectados. Si nadie la setó nunca,
    devuelve un default razonable sin persistir nada (el primer PUT lo crea)."""
    row = db.query(agenda_models.NewsletterSettings).filter(
        agenda_models.NewsletterSettings.id == 1
    ).first()
    if row:
        return {
            "edition_start_at": row.edition_start_at,
            "edition_end_at": row.edition_end_at,
        }
    return _default_edition_range()


@router.put("/newsletter-settings")
def update_newsletter_settings(
    payload: agenda_models.NewsletterSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Upsert del singleton — siempre id=1. Valida que end > start."""
    if payload.edition_end_at <= payload.edition_start_at:
        raise HTTPException(
            status_code=400,
            detail="La fecha/hora de fin tiene que ser posterior a la de inicio.",
        )
    row = db.query(agenda_models.NewsletterSettings).filter(
        agenda_models.NewsletterSettings.id == 1
    ).first()
    if row:
        row.edition_start_at = payload.edition_start_at
        row.edition_end_at = payload.edition_end_at
    else:
        row = agenda_models.NewsletterSettings(
            id=1,
            edition_start_at=payload.edition_start_at,
            edition_end_at=payload.edition_end_at,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "edition_start_at": row.edition_start_at,
        "edition_end_at": row.edition_end_at,
    }

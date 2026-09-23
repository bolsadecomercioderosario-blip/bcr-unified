"""
Módulo Agenda: CRUD de actividades + generación de copy IA + integración
con Drive (carpetas y OAuth) + webhook Santiago + CRUD de Efemérides.
"""
import os
import re
import shutil
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

import cloudinary
import cloudinary.uploader
import openai
import requests
from google_auth_oauthlib.flow import Flow
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

import agenda_models
from auth import (
    require_auth, get_role, area_of_role, is_area_role,
    ROLE_COMUNICACION, ROLE_SECRETARIA,
)
from common import require_external_integrations, require_google_drive
from config import CLOUDINARY_ENABLED, UPLOADS_DIR
from database import get_db
from utils.drive import (
    CLIENT_SECRETS_FILE, SCOPES, TOKEN_FILE,
    create_activity_folder, trash_drive_folder, untrash_drive_folder,
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
# ---------------------------------------------------------
# Visibilidad por rol (multi-área):
#   comunicacion → sus actividades + las de Secretaría + las de área APROBADAS
#                  (las que pasaron a la Mesa; les agrega sus campos operativos).
#   secretaria   → Mesa (secretaria) + todas las áreas (para ver y aprobar)
#   area:<slug>  → Mesa + todas las áreas (Mi agenda filtra a lo propio en el front)
# ---------------------------------------------------------
def _visibility_filter(query, role: str):
    A = agenda_models.Activity
    if role == ROLE_COMUNICACION:
        # No-área (comunicación + secretaría) + área aprobada.
        return query.filter(or_(A.origen != "area", A.me_estado == "aprobada"))
    # secretaria y área ven Mesa + áreas (no lo interno de Comunicación).
    return query.filter(A.origen.in_(["secretaria", "area"]))


@router.get("/actividades", response_model=List[agenda_models.ActivityOut])
def read_activities(skip: int = 0, limit: int = 500, db: Session = Depends(get_db),
                    role: str = Depends(get_role)):
    # Excluye archivadas: viven sólo en la vista "Archivados".
    q = db.query(agenda_models.Activity).filter(
        agenda_models.Activity.archived == False,  # noqa: E712 — SQLAlchemy
    )
    return _visibility_filter(q, role).offset(skip).limit(limit).all()


@router.get("/actividades/stamp")
def actividades_stamp(db: Session = Depends(get_db)):
    """Huella barata de la tabla de actividades: cantidad total + el último
    updated_at. El cliente la consulta en el polling (mucho más liviano que traer
    toda la lista) y sólo recarga la lista completa si esta huella cambió.
    Es global (no por rol): un cambio ajeno puede disparar una recarga de más,
    pero nunca omite un cambio propio."""
    count, latest = db.query(
        func.count(agenda_models.Activity.id),
        func.max(agenda_models.Activity.updated_at),
    ).one()
    return {"count": int(count or 0), "latest": latest or ""}


@router.get("/actividades/archivadas", response_model=List[agenda_models.ActivityOut])
def read_archived_activities(db: Session = Depends(get_db), role: str = Depends(get_role)):
    """Listado de actividades archivadas (soft-deleted), para la vista Archivados."""
    q = db.query(agenda_models.Activity).filter(
        agenda_models.Activity.archived == True,  # noqa: E712 — SQLAlchemy
    )
    return _visibility_filter(q, role).all()


def _owns(db_activity, role: str) -> bool:
    """¿El rol es dueño de esta actividad (puede borrarla/restaurarla)?"""
    origen = db_activity.origen or "comunicacion"
    if role == ROLE_COMUNICACION:
        return origen == "comunicacion"
    if role == ROLE_SECRETARIA:
        return origen == "secretaria"
    if is_area_role(role):
        return origen == "area" and (db_activity.area or "") == area_of_role(role)
    return False


# Grupos de campos, para permisos de edición a nivel de campo.
_GENERALS = {"date", "time", "end_date", "end_time", "title", "description",
             "location", "observations", "participants"}
_ATTACHMENT = {"attachment_url", "attachment_name"}
# Campos "propios de Comunicación" (operativo + notas internas): los agrega
# Comunicación a cualquier actividad que vea (propia, de Secretaría o de área ya
# en la Mesa), sin tocar los Datos Generales.
_OPERATIVE = {"responsible", "external_name", "channels", "done", "drive_bcr",
              "drive_santiago", "copy_instagram", "copy_linkedin", "story_type",
              "comunicacion_notes"}
# Campos del armado del newsletter Conectados. Comunicación cura el newsletter
# para TODAS las actividades que ve (propias, de Secretaría o de área ya en la
# Mesa); estos campos son propios del newsletter y NO tocan los Datos Generales
# de la actividad (el título/cuerpo de Conectados es independiente del de la
# Agenda), por eso van aparte y sólo los edita Comunicación.
_NEWSLETTER = {"conectados_title", "conectados_text", "image_url", "order_index", "block_type"}
# Campos "propios de Secretaría" en SUS actividades (incluye el Estado de avance
# que alimenta el semáforo).
_SEC_WORKFLOW = {"estado", "sec_responsible", "sec_responsible_other", "sec_notes"}
# Lo que Secretaría edita en una actividad de ÁREA: su seguimiento SIN Estado de
# avance, + "Participa (por Mesa Ejecutiva)" + sus notas internas.
_SEC_AREA = {"sec_responsible", "sec_responsible_other", "sec_notes", "participants_me"}


def _allowed_update_fields(db_activity, role: str) -> set:
    """Qué campos puede modificar `role` en esta actividad. origen/area nunca."""
    origen = db_activity.origen or "comunicacion"
    if role == ROLE_COMUNICACION:
        if origen == "comunicacion":
            return _GENERALS | _ATTACHMENT | _OPERATIVE | _NEWSLETTER
        if origen == "secretaria" or (origen == "area" and db_activity.me_estado == "aprobada"):
            return _OPERATIVE | _NEWSLETTER  # ajena: sus campos operativos + armado del newsletter
        return set()
    if role == ROLE_SECRETARIA:
        if origen == "secretaria":
            return _GENERALS | _ATTACHMENT | _SEC_WORKFLOW
        if origen == "area":
            return _SEC_AREA | {"me_estado"}   # seguimiento (sin estado) + aprobar/rechazar
        return set()
    if is_area_role(role):
        if origen == "area" and (db_activity.area or "") == area_of_role(role):
            return _GENERALS | _ATTACHMENT | {"me_estado"}
        return set()
    return set()


# --- Validación de fecha/hora y timestamp de cambios --------------------------
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_TIME_SPECIALS = {"", "A definir", "Sin horario"}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _is_real_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _validate_datetime_fields(data: dict) -> None:
    """Valida SÓLO las claves de fecha/hora presentes en `data`. La fecha (date)
    debe ser YYYY-MM-DD real; end_date igual pero puede ir vacía; time/end_time
    deben ser HH:MM o un valor especial ('A definir'/'Sin horario') o vacío.
    Levanta 400 si algo no cumple (evita guardar basura que rompa el orden)."""
    if "date" in data:
        v = (data["date"] or "").strip()
        if not _DATE_RE.match(v) or not _is_real_date(v):
            raise HTTPException(status_code=400, detail="La fecha debe tener formato YYYY-MM-DD válido.")
    if "end_date" in data:
        v = (data["end_date"] or "").strip()
        if v and (not _DATE_RE.match(v) or not _is_real_date(v)):
            raise HTTPException(status_code=400, detail="La fecha de fin debe tener formato YYYY-MM-DD válido.")
    for k in ("time", "end_time"):
        if k in data:
            v = (data[k] or "").strip()
            if v not in _TIME_SPECIALS and not _TIME_RE.match(v):
                raise HTTPException(status_code=400, detail="La hora debe tener formato HH:MM (o 'A definir' / 'Sin horario').")


@router.post("/actividades", response_model=agenda_models.ActivityOut)
def create_activity(activity: agenda_models.ActivityCreate, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db), role: str = Depends(get_role)):
    data = activity.model_dump()
    _validate_datetime_fields(data)
    # El ID lo genera el SERVIDOR (UUID): no se confía en el que manda el cliente
    # (evita colisiones/spoofing). El front reconcilia por el id que devolvemos.
    data["id"] = uuid.uuid4().hex
    data["updated_at"] = _now_iso()
    # El origen/dueño lo fija el rol (no se confía en lo que manda el cliente).
    if role == ROLE_COMUNICACION:
        data["origen"] = "comunicacion"; data["area"] = ""; data["me_estado"] = ""
    elif role == ROLE_SECRETARIA:
        data["origen"] = "secretaria"; data["area"] = ""; data["me_estado"] = ""
    elif is_area_role(role):
        data["origen"] = "area"; data["area"] = area_of_role(role)
        # Un área sólo puede dejar la sugerencia en pendiente (no auto-aprobarse).
        data["me_estado"] = "pendiente" if (data.get("me_estado") or "") else ""
    else:
        raise HTTPException(status_code=403, detail="Rol sin permiso de carga")

    db_activity = agenda_models.Activity(**data)
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return db_activity


@router.put("/actividades/{activity_id}", response_model=agenda_models.ActivityOut)
def update_activity(activity_id: str, activity: agenda_models.ActivityUpdate, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db), role: str = Depends(get_role)):
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    allowed = _allowed_update_fields(db_activity, role)
    if not allowed:
        raise HTTPException(status_code=403, detail="No podés editar esta actividad")

    # Sólo se aplican los campos permitidos para este rol (origen/area nunca).
    update_data = {k: v for k, v in activity.model_dump(exclude_unset=True).items() if k in allowed}

    if "me_estado" in update_data:
        if is_area_role(role):
            # El área no puede auto-aprobarse: si ya está aprobada, se mantiene;
            # si no, sólo puede dejarla en pendiente o sin sugerir.
            update_data["me_estado"] = ("aprobada" if db_activity.me_estado == "aprobada"
                                        else ("pendiente" if (update_data["me_estado"] or "") else ""))
        else:  # secretaria aprueba/rechaza/revierte
            if update_data["me_estado"] not in ("pendiente", "aprobada", "rechazada", ""):
                raise HTTPException(status_code=400, detail="Estado de Mesa inválido")
            update_data["me_estado"] = update_data["me_estado"] or ""

    _validate_datetime_fields(update_data)

    for key, value in update_data.items():
        setattr(db_activity, key, value)

    db_activity.updated_at = _now_iso()
    db.commit()
    db.refresh(db_activity)
    return db_activity


@router.post("/actividades/{activity_id}/notify-santiago")
def notify_santiago(activity_id: str, payload: dict, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db), role: str = Depends(get_role)):
    require_external_integrations()
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    # Sólo quien puede editar el campo operativo drive_santiago de ESTA actividad
    # (no cualquier token autenticado) — evita IDOR sobre actividades ajenas.
    if "drive_santiago" not in _allowed_update_fields(db_activity, role):
        raise HTTPException(status_code=403, detail="No podés operar sobre esta actividad")

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
def manual_create_folder(activity_id: str, db: Session = Depends(get_db), role: str = Depends(get_role)):
    require_google_drive()
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    # Sólo quien puede editar drive_bcr de ESTA actividad (evita IDOR).
    if "drive_bcr" not in _allowed_update_fields(db_activity, role):
        raise HTTPException(status_code=403, detail="No podés operar sobre esta actividad")

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
def archive_activity(activity_id: str, hard: bool = False, db: Session = Depends(get_db),
                     role: str = Depends(get_role)):
    """Archiva la actividad (soft-delete): NO borra el registro, lo marca como
    archivado y sale de todas las vistas activas. La carpeta de Drive va a la
    PAPELERA (recuperable). Todo se puede restaurar desde la vista Archivados.

    `hard=true` SÓLO se acepta para bloques de newsletter (is_custom): son piezas
    del Conectados, no actividades de la agenda, y se borran de verdad. Para una
    actividad real se archiva igual, aunque venga hard=true (nunca se borra por
    accidente desde Conectados)."""
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Sólo el dueño archiva lo suyo (cada área lo suyo; Secretaría lo de Mesa;
    # Comunicación lo suyo, incluidos los bloques de newsletter is_custom).
    if not _owns(db_activity, role):
        raise HTTPException(status_code=403, detail="No podés eliminar esta actividad")

    if hard and db_activity.is_custom:
        db.delete(db_activity)
        db.commit()
        return {"ok": True, "deleted": True}

    if db_activity.drive_bcr:
        trash_drive_folder(db_activity.drive_bcr)
    if db_activity.drive_santiago:
        trash_drive_folder(db_activity.drive_santiago)

    db_activity.archived = True
    db_activity.archived_at = datetime.utcnow().isoformat()
    db_activity.updated_at = _now_iso()
    db.commit()
    return {"ok": True}


@router.post("/actividades/{activity_id}/restore", response_model=agenda_models.ActivityOut)
def restore_activity(activity_id: str, db: Session = Depends(get_db), role: str = Depends(get_role)):
    """Restaura una actividad archivada: vuelve a las vistas activas y saca su
    carpeta de Drive de la papelera."""
    db_activity = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not _owns(db_activity, role):
        raise HTTPException(status_code=403, detail="No podés restaurar esta actividad")

    if db_activity.drive_bcr:
        untrash_drive_folder(db_activity.drive_bcr)
    if db_activity.drive_santiago:
        untrash_drive_folder(db_activity.drive_santiago)

    db_activity.archived = False
    db_activity.archived_at = ""
    db_activity.updated_at = _now_iso()
    db.commit()
    db.refresh(db_activity)
    return db_activity


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

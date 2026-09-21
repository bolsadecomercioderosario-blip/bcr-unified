"""
Carga de actividades en la Agenda por WhatsApp (voz o texto).

Flujo:
  1. Un número "writer" (mapeado a un rol en BOT_AGENDA_WRITERS) manda un AUDIO.
  2. Se descarga y transcribe (OpenAI), y de la transcripción se extraen los
     campos de la actividad (título, fecha, hora, lugar, participantes).
  3. El bot responde con un resumen y pide CONFIRMACIÓN ("respondé SÍ").
  4. Si confirma, se crea la actividad en la Agenda con el origen del rol
     (secretaria → Mesa Ejecutiva; area:<slug> → sugerencia pendiente del área).

Es la primera acción de ESCRITURA del bot. La identidad la garantiza la firma de
Twilio (validada en el webhook) + el mapeo por número. Sólo números de confianza.
"""
from __future__ import annotations

import io
import json
import re
import uuid
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

import agenda_models
from database import SessionLocal
from config import BOT_AGENDA_WRITERS, BOT_OPENAI_API_KEY, BOT_OPENAI_MODEL
from bot import twilio_client


_ARG = timedelta(hours=3)  # ART = UTC-3 (sin DST)
_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _now_art() -> datetime:
    return datetime.utcnow() - _ARG


# --- Mapeo número → rol -----------------------------------------------------
def _norm_phone(p: str) -> str:
    return re.sub(r"\D", "", p or "")


def _parse_writers(raw: str) -> dict:
    out = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        phone, role = item.split("=", 1)
        phone = _norm_phone(phone)
        role = role.strip()
        if phone and role:
            out[phone] = role
    return out


_WRITERS = _parse_writers(BOT_AGENDA_WRITERS)


def writer_role(from_phone: str) -> Optional[str]:
    """Rol del número si está habilitado a escribir; None si no."""
    return _WRITERS.get(_norm_phone(from_phone))


# --- Borradores pendientes de confirmación (en memoria, acotado) ------------
# {phone_norm: {"draft": {...}, "at": datetime}}. Se descartan a los 30 min.
_PENDING: dict = {}
_PENDING_TTL = timedelta(minutes=30)


def has_pending(from_phone: str) -> bool:
    key = _norm_phone(from_phone)
    row = _PENDING.get(key)
    if not row:
        return False
    if datetime.utcnow() - row["at"] > _PENDING_TTL:
        _PENDING.pop(key, None)
        return False
    return True


def _set_pending(from_phone: str, draft: dict) -> None:
    _PENDING[_norm_phone(from_phone)] = {"draft": draft, "at": datetime.utcnow()}


def _pop_pending(from_phone: str) -> Optional[dict]:
    row = _PENDING.pop(_norm_phone(from_phone), None)
    return row["draft"] if row else None


# --- OpenAI -----------------------------------------------------------------
def _client():
    if not BOT_OPENAI_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=BOT_OPENAI_API_KEY, timeout=60.0, max_retries=1)


def _ext_for(media_type: str) -> str:
    mt = (media_type or "").lower()
    if "ogg" in mt or "opus" in mt:
        return "audio.ogg"
    if "mpeg" in mt or "mp3" in mt:
        return "audio.mp3"
    if "wav" in mt:
        return "audio.wav"
    if "mp4" in mt or "m4a" in mt or "aac" in mt:
        return "audio.m4a"
    return "audio.ogg"  # WhatsApp manda ogg/opus por defecto


def _transcribe(audio_bytes: bytes, media_type: str) -> Optional[str]:
    c = _client()
    if not c:
        return None
    f = io.BytesIO(audio_bytes)
    f.name = _ext_for(media_type)
    try:
        r = c.audio.transcriptions.create(model="whisper-1", file=f, language="es")
        return (getattr(r, "text", "") or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] transcripción falló: {type(exc).__name__}: {exc}")
        return None


_EXTRACT_PROMPT = """\
Sos un asistente que arma una actividad de agenda a partir de lo que dijo una \
persona. Hoy es {hoy} ({dia_semana}), horario de Argentina.

De este texto, extraé los datos de la actividad y devolvé SÓLO un JSON (sin texto \
alrededor, sin ```), con exactamente estas claves:
- "title": título breve de la actividad (obligatorio).
- "date": fecha en formato YYYY-MM-DD. Resolvé expresiones relativas ("mañana", \
"el martes que viene", "el 20") a la fecha concreta. Si no se menciona ninguna \
fecha, dejá "".
- "time": hora de inicio en formato HH:MM (24h), o "" si no se menciona.
- "end_time": hora de fin HH:MM, o "".
- "location": lugar, o "".
- "participants": personas/áreas que participan, o "".
- "description": detalle adicional, o "".

Texto: {texto}
"""


def _extract(texto: str) -> Optional[dict]:
    c = _client()
    if not c:
        return None
    now = _now_art()
    prompt = _EXTRACT_PROMPT.format(
        hoy=now.strftime("%Y-%m-%d"),
        dia_semana=_WEEKDAYS[now.weekday()],
        texto=texto,
    )
    try:
        r = c.responses.create(model=BOT_OPENAI_MODEL, input=prompt)
        raw = (getattr(r, "output_text", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] extracción falló: {type(exc).__name__}: {exc}")
        return None
    # Sacamos posibles fences ```json ... ```
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        print(f"[agenda_writer] JSON inválido del LLM: {raw!r}")
        return None
    if not isinstance(data, dict):
        return None
    # Normalizamos claves esperadas.
    return {
        "title": (data.get("title") or "").strip(),
        "date": (data.get("date") or "").strip(),
        "time": (data.get("time") or "").strip(),
        "end_time": (data.get("end_time") or "").strip(),
        "location": (data.get("location") or "").strip(),
        "participants": (data.get("participants") or "").strip(),
        "description": (data.get("description") or "").strip(),
    }


# --- Resumen para confirmar -------------------------------------------------
def _fmt_fecha(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{_WEEKDAYS[d.weekday()]} {d.day}/{d.month}/{d.year}"
    except Exception:  # noqa: BLE001
        return iso or "(sin fecha)"


def _resumen(draft: dict) -> str:
    lineas = [f"📌 *{draft.get('title') or '(sin título)'}*"]
    lineas.append(f"📅 {_fmt_fecha(draft.get('date',''))}")
    hora = draft.get("time") or ""
    if hora:
        hora_txt = f"{hora} a {draft['end_time']}" if draft.get("end_time") else hora
        lineas.append(f"🕒 {hora_txt}")
    else:
        lineas.append("🕒 (sin horario)")
    if draft.get("location"):
        lineas.append(f"📍 {draft['location']}")
    if draft.get("participants"):
        lineas.append(f"👥 {draft['participants']}")
    if draft.get("description"):
        lineas.append(f"📝 {draft['description']}")
    return "\n".join(lineas)


# --- Crear la actividad -----------------------------------------------------
def _create_activity(role: str, draft: dict) -> None:
    db = SessionLocal()
    try:
        origen, area, me_estado = "secretaria", "", ""
        if role.startswith("area:"):
            origen, area, me_estado = "area", role.split(":", 1)[1], "pendiente"
        elif role == "comunicacion":
            origen = "comunicacion"
        act = agenda_models.Activity(
            id=uuid.uuid4().hex,
            date=draft.get("date") or _now_art().strftime("%Y-%m-%d"),
            time=draft.get("time") or "A definir",
            end_date="",
            end_time=draft.get("end_time") or "",
            title=draft.get("title") or "(sin título)",
            description=draft.get("description") or "",
            location=draft.get("location") or "",
            participants=draft.get("participants") or "",
            channels=[],
            origen=origen,
            area=area,
            me_estado=me_estado,
        )
        db.add(act)
        db.commit()
    finally:
        db.close()


# --- Confirmación (sí / no) -------------------------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


_YES = {"si", "s", "dale", "ok", "oka", "okay", "confirmo", "confirmar", "sip",
        "sisi", "va", "listo", "perfecto", "de una", "correcto", "asi es"}
_NO = {"no", "nop", "cancelar", "cancela", "cancelalo", "borrar", "descartar",
       "nada", "negativo"}


# --- Handlers (llamados desde el webhook, en segundo plano) -----------------
def handle_voice(from_phone: str, role: str, media_url: str, media_type: str, ev: dict) -> None:
    """Descarga+transcribe el audio, extrae la actividad y pide confirmación."""
    try:
        audio, ctype = twilio_client.download_media(media_url)
        media_type = media_type or ctype
        texto = _transcribe(audio, media_type)
        if not texto:
            twilio_client.send_whatsapp(from_phone, "No pude entender el audio. ¿Lo probás de nuevo, más claro?")
            ev["outcome"] = "writer_audio_vacio"
            return
        ev["transcripcion_len"] = len(texto)
        draft = _extract(texto)
        if not draft or not draft.get("title") or not draft.get("date"):
            falta = "el título" if (draft and not draft.get("title")) else "la fecha"
            twilio_client.send_whatsapp(
                from_phone,
                f"Entendí: \"{texto}\"\n\nPero me faltó {falta}. ¿Me mandás un audio "
                "diciendo qué actividad es y para cuándo?",
            )
            ev["outcome"] = "writer_incompleto"
            return
        _set_pending(from_phone, draft)
        twilio_client.send_whatsapp(
            from_phone,
            "Voy a cargar esta actividad en la Agenda de la Mesa Ejecutiva:\n\n"
            f"{_resumen(draft)}\n\n¿La confirmo? Respondé *SÍ* para cargarla, o *NO* para descartar.",
        )
        ev["outcome"] = "writer_pendiente"
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] handle_voice error: {type(exc).__name__}: {exc}")
        ev["error"] = f"writer_voice: {type(exc).__name__}: {exc}"
        try:
            twilio_client.send_whatsapp(from_phone, "Tuve un problema procesando el audio. Probá de nuevo en un momento.")
        except Exception:  # noqa: BLE001
            pass


def handle_confirmation(from_phone: str, body: str, role: str, ev: dict) -> None:
    """Procesa el SÍ/NO cuando hay un borrador pendiente."""
    resp = _norm(body)
    if resp in _YES:
        draft = _pop_pending(from_phone)
        if not draft:
            twilio_client.send_whatsapp(from_phone, "No tengo ninguna actividad pendiente de confirmar. Mandame un audio con la actividad.")
            ev["outcome"] = "writer_sin_pendiente"
            return
        try:
            _create_activity(role, draft)
            twilio_client.send_whatsapp(from_phone, f"✅ Actividad cargada:\n\n{_resumen(draft)}")
            ev["outcome"] = "writer_cargada"
        except Exception as exc:  # noqa: BLE001
            print(f"[agenda_writer] _create_activity error: {type(exc).__name__}: {exc}")
            ev["error"] = f"writer_create: {type(exc).__name__}: {exc}"
            twilio_client.send_whatsapp(from_phone, "No pude guardar la actividad. Probá de nuevo.")
        return
    if resp in _NO:
        _pop_pending(from_phone)
        twilio_client.send_whatsapp(from_phone, "Listo, la descarté. Si querés, mandame otro audio con la actividad.")
        ev["outcome"] = "writer_descartada"
        return
    # Cualquier otra cosa: mantenemos el pendiente y aclaramos.
    twilio_client.send_whatsapp(from_phone, "¿Cargo la actividad? Respondé *SÍ* o *NO*.")
    ev["outcome"] = "writer_confirm_ambiguo"

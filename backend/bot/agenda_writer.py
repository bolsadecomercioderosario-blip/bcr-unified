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
from bot.db_models import BotConfig


_ARG = timedelta(hours=3)  # ART = UTC-3 (sin DST)
_WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _now_art() -> datetime:
    return datetime.utcnow() - _ARG


# --- Mapeo número → rol -----------------------------------------------------
def _norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    # Argentina: colapsar el "9" de celular después del 54 (Meta/Twilio mandan
    # ambas formas), para que el número matchee lo cargues como lo cargues.
    if d.startswith("549"):
        d = "54" + d[3:]
    return d


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
# El "state" guarda en qué punto de la conversación está el writer:
#   {"mode": "crear",   "draft": {...}}                         → confirmar alta
#   {"mode": "editar",  "draft": {...}, "id": "<act>"}          → confirmar edición
#   {"mode": "cancelar","draft": {...}, "id": "<act>"}          → confirmar baja
#   {"mode": "select",  "purpose": "editar"|"cancelar", "options": [{n,id,label}]}


def _get_state(from_phone: str) -> Optional[dict]:
    key = _norm_phone(from_phone)
    row = _PENDING.get(key)
    if not row:
        return None
    if datetime.utcnow() - row["at"] > _PENDING_TTL:
        _PENDING.pop(key, None)
        return None
    return row["state"]


def has_pending(from_phone: str) -> bool:
    return _get_state(from_phone) is not None


def _set_state(from_phone: str, state: dict) -> None:
    _PENDING[_norm_phone(from_phone)] = {"state": state, "at": datetime.utcnow()}


def _clear_state(from_phone: str) -> None:
    _PENDING.pop(_norm_phone(from_phone), None)


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


# Campos que el bot carga desde WhatsApp. A propósito NO incluye "participants"
# (ese campo es "quién participa por BCR" y se completa desde la app, no se infiere
# de lo que se dice) ni otros. Obligatorios: fecha, hora y título.
_FIELDS = ("title", "date", "time", "location", "description")
_REQUIRED = (("title", "el título"), ("date", "la fecha"), ("time", "la hora"))


def _llm_json(prompt: str) -> Optional[dict]:
    """Corre el LLM y parsea su respuesta como JSON (tolerando fences ```)."""
    c = _client()
    if not c:
        return None
    try:
        r = c.responses.create(model=BOT_OPENAI_MODEL, input=prompt)
        raw = (getattr(r, "output_text", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] LLM falló: {type(exc).__name__}: {exc}")
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        print(f"[agenda_writer] JSON inválido del LLM: {raw!r}")
        return None
    return data if isinstance(data, dict) else None


def _clean_fields(data: dict) -> dict:
    return {k: (str(data.get(k) or "")).strip() for k in _FIELDS}


_UNDERSTAND_PROMPT = """\
Sos el asistente de la Secretaría de la Bolsa de Comercio de Rosario. Hoy es \
{hoy} ({dia_semana}), horario de Argentina. La persona te mandó este mensaje.

Decidí qué quiere y devolvé SÓLO un JSON (sin texto alrededor, sin ```):
- "intent": uno de:
  "crear"    → está describiendo una actividad NUEVA para agendar.
  "editar"   → quiere MODIFICAR una actividad ya cargada (ej. "editar la agenda",
               "cambiar una actividad", "modificar la reunión de mañana").
  "cancelar" → quiere CANCELAR/eliminar una actividad ya cargada.
  "otro"     → saludo, consulta, o cualquier otra cosa.
- Si "intent" es "crear", agregá EXACTAMENTE estas claves (y ninguna más):
  "title": título de la actividad. Incluí el evento completo tal como se dice, por \
ejemplo "Reunión con el Ministro de Economía" va ENTERO en el título. No separes a \
nadie como participante.
  "date": fecha YYYY-MM-DD, resolviendo expresiones relativas ("mañana", "el martes \
que viene"); "" si no se menciona.
  "time": hora de inicio HH:MM (24h); "" si no se menciona.
  "location": lugar; "" si no se menciona.
  "description": detalle adicional si lo hay; "" si no.
- Si "intent" es "editar" o "cancelar", agregá SOLO la clave "date" (YYYY-MM-DD del \
día de la actividad a modificar, resolviendo relativas; "" si no se menciona un día).

Importante: para "crear" NO infieras participantes ni ningún otro dato.

Mensaje: {texto}
"""


def _understand(texto: str) -> Optional[dict]:
    """Devuelve {intent, ...campos}. None si el LLM no está disponible/falló."""
    now = _now_art()
    data = _llm_json(_UNDERSTAND_PROMPT.format(
        hoy=now.strftime("%Y-%m-%d"), dia_semana=_WEEKDAYS[now.weekday()], texto=texto,
    ))
    if data is None:
        return None
    intent = (data.get("intent") or "").strip().lower()
    if intent not in ("crear", "editar", "cancelar"):
        intent = "otro"
    out = {"intent": intent}
    out.update(_clean_fields(data))
    return out


_EDIT_PROMPT = """\
Tenés una actividad en preparación (JSON). La persona pide un cambio. Devolvé SÓLO \
el JSON actualizado (sin texto alrededor, sin ```), con EXACTAMENTE las mismas \
claves, aplicando el cambio pedido y dejando el resto igual. Hoy es {hoy}; resolvé \
fechas relativas con eso.

Actividad actual: {actual}
Cambio pedido: {cambio}
"""


def _apply_edit(draft: dict, instruction: str) -> Optional[dict]:
    now = _now_art()
    data = _llm_json(_EDIT_PROMPT.format(
        hoy=now.strftime("%Y-%m-%d"),
        actual=json.dumps({k: draft.get(k, "") for k in _FIELDS}, ensure_ascii=False),
        cambio=instruction,
    ))
    if data is None:
        return None
    return _clean_fields(data)


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
    lineas.append(f"🕒 {draft.get('time') or '(sin horario)'}")
    if draft.get("location"):
        lineas.append(f"📍 {draft['location']}")
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
            end_time="",
            title=draft.get("title") or "(sin título)",
            description=draft.get("description") or "",
            location=draft.get("location") or "",
            participants="",   # se completa desde la app (quién participa por BCR)
            channels=[],
            origen=origen,
            area=area,
            me_estado=me_estado,
        )
        db.add(act)
        db.commit()
    finally:
        db.close()


# --- Editar / cancelar actividades existentes -------------------------------
def _act_to_draft(act) -> dict:
    """Campos editables de una Activity en el formato de draft."""
    return {
        "title": act.title or "",
        "date": act.date or "",
        "time": "" if (act.time in (None, "", "A definir", "Sin horario", "00:00")) else act.time,
        "location": act.location or "",
        "description": act.description or "",
    }


def _list_me_activities(day_iso: str) -> list:
    """Actividades de la Mesa Ejecutiva (origen=secretaria, no archivadas) de un
    día, ordenadas por hora. Devuelve [{id, label, draft}]."""
    db = SessionLocal()
    try:
        A = agenda_models.Activity
        rows = db.query(A).filter(
            A.origen == "secretaria", A.archived == False, A.date == day_iso,  # noqa: E712
        ).all()
        rows.sort(key=lambda a: (a.time or "99:99"))
        out = []
        for a in rows:
            d = _act_to_draft(a)
            hora = d["time"] or "sin horario"
            lugar = f" · {d['location']}" if d["location"] else ""
            out.append({"id": a.id, "label": f"{d['title']} · {hora}{lugar}", "draft": d})
        return out
    finally:
        db.close()


def _update_activity(act_id: str, draft: dict) -> bool:
    db = SessionLocal()
    try:
        a = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == act_id).first()
        if not a:
            return False
        a.title = draft.get("title") or a.title
        a.date = draft.get("date") or a.date
        a.time = draft.get("time") or "A definir"
        a.location = draft.get("location") or ""
        a.description = draft.get("description") or ""
        db.commit()
        return True
    finally:
        db.close()


def _archive_activity(act_id: str) -> bool:
    """Baja (soft-delete): marca la actividad como archivada. No la borra de la DB."""
    db = SessionLocal()
    try:
        a = db.query(agenda_models.Activity).filter(agenda_models.Activity.id == act_id).first()
        if not a:
            return False
        a.archived = True
        a.archived_at = datetime.utcnow().isoformat()
        db.commit()
        return True
    finally:
        db.close()


def _parse_selection(text: str):
    """De 'la 2, cambiá la hora a las 18' saca (2, 'cambiá la hora a las 18').
    Devuelve (None, '') si no hay un número al principio."""
    m = re.match(r"\s*(?:la\s+|el\s+|numero\s+|n[º°]?\s*)?(\d{1,2})\b[\s.,:;-]*(.*)", text or "", re.IGNORECASE)
    if not m:
        return None, ""
    return int(m.group(1)), (m.group(2) or "").strip()


# --- Confirmación (sí / no) -------------------------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)   # saca puntuación (comas, etc.)
    return " ".join(s.split())


# Incluye los ids de los botones ("si"/"no") y sus TÍTULOS ("Sí, cargar" /
# "No, descartar"), porque al tocar un botón WhatsApp puede mandar el título.
_YES = {"si", "s", "si cargar", "cargar", "cargala", "dale", "ok", "oka", "okay",
        "confirmo", "confirmar", "sip", "sisi", "va", "listo", "perfecto",
        "de una", "correcto", "asi es"}
_NO = {"no", "no descartar", "nop", "cancelar", "cancela", "cancelalo", "borrar",
       "descartar", "nada", "negativo"}

# Saludos → mensaje de bienvenida propio del writer (no el menú de lectura).
_GREETINGS = {"hola", "holaa", "holis", "buenas", "buenass", "buen dia",
              "buenos dias", "buenas tardes", "buenas noches", "menu", "opciones",
              "inicio", "empezar", "comenzar", "hi", "hello", "ayuda", "que onda"}

_WELCOME = (
    "Puedo ayudarte con la agenda de la Mesa Ejecutiva:\n"
    "• Para *cargar* una actividad: mandame un audio o escribila (qué es, cuándo y dónde).\n"
    "• Para *editar* o *cancelar* una ya cargada: decime \"editar\" o \"cancelar\"."
)


def _missing_required(draft: dict) -> list:
    """Lista de etiquetas de los campos obligatorios que faltan (título/fecha/hora)."""
    return [label for key, label in _REQUIRED if not (draft.get(key) or "").strip()]


def _y_join(items: list) -> str:
    """['la fecha','la hora'] → 'la fecha y la hora'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " y " + items[-1]


# --- Confirmación con botones (quick-reply Sí/No) ---------------------------
def ensure_confirm_content_sid() -> Optional[str]:
    """SID del template de botones Sí/No; lo crea y persiste la primera vez."""
    db = SessionLocal()
    try:
        row = db.query(BotConfig).filter(BotConfig.key == "confirm_content_sid_v2").first()
        if row and row.value:
            return row.value
        sid = twilio_client.create_confirm_content_sid()
        if row:
            row.value = sid
            row.updated_at = datetime.utcnow()
        else:
            db.add(BotConfig(key="confirm_content_sid_v2", value=sid))
        db.commit()
        return sid
    finally:
        db.close()


def _send_confirmation(from_phone: str, draft: dict, encabezado: str) -> None:
    """Manda el resumen + botones Sí/No. Si el template falla, cae a texto."""
    full = f"{encabezado}\n\n{_resumen(draft)}"
    try:
        sid = ensure_confirm_content_sid()
        if sid:
            twilio_client.send_whatsapp_content(from_phone, sid, {"1": full})
            return
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] botones confirmación fallaron, fallback a texto: {exc}")
    twilio_client.send_whatsapp(from_phone, full + "\n\n¿La confirmo? Respondé *SÍ* o *NO*.")


# --- Núcleo: procesa un mensaje (texto ya transcripto si vino por audio) -----
def _send(from_phone: str, msg: str) -> None:
    twilio_client.send_whatsapp(from_phone, msg)


def _core(from_phone: str, role: str, text: str, ev: dict) -> None:
    text = (text or "").strip()
    if not text:
        return
    state = _get_state(from_phone)
    if state:
        _handle_pending(from_phone, role, text, state, ev)
        return

    # Sin estado: saludo → bienvenida; si no, entendemos la intención.
    if _norm(text) in _GREETINGS:
        _send(from_phone, _WELCOME)
        ev["outcome"] = "writer_bienvenida"
        return
    u = _understand(text)
    if u is None:
        _send(from_phone, "No pude procesar el mensaje en este momento. Probá de nuevo.")
        ev["outcome"] = "writer_llm_off"
        return
    intent = u["intent"]
    if intent == "crear":
        _start_create(from_phone, u, ev)
    elif intent in ("editar", "cancelar"):
        _start_select(from_phone, intent, u.get("date", ""), ev)
    else:
        _send(from_phone, _WELCOME)
        ev["outcome"] = "writer_otro"


def _start_create(from_phone: str, u: dict, ev: dict) -> None:
    draft = {k: u[k] for k in _FIELDS}
    faltan = _missing_required(draft)
    if faltan:
        _send(from_phone, f"Para cargar la actividad me falta {_y_join(faltan)}. "
                          "Decime al menos el título, la fecha y la hora.")
        ev["outcome"] = "writer_incompleto"
        return
    _set_state(from_phone, {"mode": "crear", "draft": draft})
    _send_confirmation(from_phone, draft, "Voy a cargar esta actividad en la Agenda de la Mesa Ejecutiva:")
    ev["outcome"] = "writer_pendiente"


def _start_select(from_phone: str, purpose: str, date_iso: str, ev: dict) -> None:
    day = date_iso or _now_art().strftime("%Y-%m-%d")
    opts = _list_me_activities(day)
    if not opts:
        _send(from_phone, f"No hay actividades de la Mesa Ejecutiva para el {_fmt_fecha(day)}. "
                          "Podés decirme otro día (ej: \"editar la agenda de mañana\").")
        ev["outcome"] = "writer_sin_actividades"
        return
    options = [{"n": i + 1, "id": o["id"], "label": o["label"], "draft": o["draft"]}
               for i, o in enumerate(opts)]
    _set_state(from_phone, {"mode": "select", "purpose": purpose, "options": options})
    verbo = "editar" if purpose == "editar" else "cancelar"
    lineas = [f"Actividades de la Mesa Ejecutiva — {_fmt_fecha(day)}:"]
    lineas += [f"{o['n']}. {o['label']}" for o in options]
    extra = " (podés incluir el cambio, ej: \"2, la hora a las 18\")" if purpose == "editar" else ""
    lineas.append(f"\nDecime el número de la que querés {verbo}{extra}.")
    _send(from_phone, "\n".join(lineas))
    ev["outcome"] = f"writer_lista_{purpose}"


def _handle_pending(from_phone: str, role: str, text: str, state: dict, ev: dict) -> None:
    mode = state.get("mode")

    # Elegir un número de la lista (para editar o cancelar).
    if mode == "select":
        if _norm(text) in _NO:
            _clear_state(from_phone)
            _send(from_phone, "Ok, no toco nada. Si querés, decime \"editar\" o \"cancelar\" de nuevo.")
            ev["outcome"] = "writer_select_abort"
            return
        num, rest = _parse_selection(text)
        if num is None:
            _send(from_phone, "Decime el *número* de la actividad de la lista (por ejemplo: 2).")
            ev["outcome"] = "writer_select_nonum"
            return
        opt = next((o for o in state["options"] if o["n"] == num), None)
        if not opt:
            _send(from_phone, f"No hay una opción {num} en la lista. Fijate los números.")
            ev["outcome"] = "writer_select_badnum"
            return
        draft = dict(opt["draft"])
        if state["purpose"] == "cancelar":
            _set_state(from_phone, {"mode": "cancelar", "id": opt["id"], "draft": draft})
            _send_confirmation(from_phone, draft, "Voy a CANCELAR esta actividad:")
            ev["outcome"] = "writer_cancel_confirm"
            return
        # editar: si vino un cambio junto al número, lo aplico y muestro preview
        if rest:
            updated = _apply_edit(draft, rest)
            if updated and updated.get("title"):
                _set_state(from_phone, {"mode": "editar", "id": opt["id"], "draft": updated})
                _send_confirmation(from_phone, updated, "Así quedaría la actividad:")
                ev["outcome"] = "writer_edit_preview"
                return
        _set_state(from_phone, {"mode": "editar", "id": opt["id"], "draft": draft})
        _send(from_phone, f"Seleccionaste:\n\n{_resumen(draft)}\n\n¿Qué querés cambiar? "
                          "(ej: \"la hora a las 18\")")
        ev["outcome"] = "writer_edit_selected"
        return

    resp = _norm(text)

    # Confirmar una CANCELACIÓN.
    if mode == "cancelar":
        if resp in _YES:
            ok = _archive_activity(state["id"])
            _clear_state(from_phone)
            if ok:
                _send(from_phone, f"✅ Actividad cancelada:\n\n{_resumen(state['draft'])}")
                ev["outcome"] = "writer_cancelada"
            else:
                _send(from_phone, "No encontré esa actividad (puede que ya no esté).")
                ev["outcome"] = "writer_cancel_notfound"
            return
        if resp in _NO:
            _clear_state(from_phone)
            _send(from_phone, "Listo, no la cancelé.")
            ev["outcome"] = "writer_cancel_abort"
            return
        _send(from_phone, "¿Cancelo la actividad? Respondé *SÍ* o *NO*.")
        return

    # Confirmar un ALTA (crear) o una EDICIÓN.
    if resp in _YES:
        draft = state["draft"]
        try:
            if mode == "crear":
                _create_activity(role, draft)
                msg = "✅ Actividad cargada:"
                ev["outcome"] = "writer_cargada"
            else:  # editar
                _update_activity(state["id"], draft)
                msg = "✅ Actividad actualizada:"
                ev["outcome"] = "writer_actualizada"
            _clear_state(from_phone)
            _send(from_phone, f"{msg}\n\n{_resumen(draft)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[agenda_writer] guardar ({mode}) error: {type(exc).__name__}: {exc}")
            ev["error"] = f"writer_save: {type(exc).__name__}: {exc}"
            _send(from_phone, "No pude guardar la actividad. Probá de nuevo.")
        return
    if resp in _NO:
        _clear_state(from_phone)
        _send(from_phone, "Listo, lo descarté. Si querés, mandame otra cosa.")
        ev["outcome"] = "writer_descartada"
        return

    # Cualquier otra cosa: es una CORRECCIÓN al borrador.
    updated = _apply_edit(state["draft"], text)
    if not updated or not updated.get("title"):
        _send(from_phone, "No pude aplicar ese cambio. ¿Me lo decís de otra forma?")
        ev["outcome"] = "writer_edit_fallo"
        return
    new_state = dict(state)
    new_state["draft"] = updated
    _set_state(from_phone, new_state)
    _send_confirmation(from_phone, updated, "Actualicé la actividad:")
    ev["outcome"] = "writer_editada"


# --- Handlers (llamados desde el webhook, en segundo plano) -----------------
def handle_text(from_phone: str, role: str, text: str, ev: dict) -> None:
    """Mensaje de texto de un writer: crear / corregir / confirmar."""
    try:
        _core(from_phone, role, text, ev)
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] handle_text error: {type(exc).__name__}: {exc}")
        ev["error"] = f"writer_text: {type(exc).__name__}: {exc}"


def transcribe(media_url: str, media_type: str = "") -> Optional[str]:
    """Descarga un audio de Twilio y devuelve su transcripción (o None). Reutilizable
    también para las CONSULTAS por voz de los miembros de la ME (no sólo writers)."""
    audio, ctype = twilio_client.download_media(media_url)
    return _transcribe(audio, media_type or ctype)


def handle_voice(from_phone: str, role: str, media_url: str, media_type: str, ev: dict) -> None:
    """Audio de un writer: se transcribe y sigue el mismo flujo que el texto."""
    try:
        texto = transcribe(media_url, media_type)
        if not texto:
            twilio_client.send_whatsapp(from_phone, "No pude entender el audio. ¿Lo probás de nuevo, más claro?")
            ev["outcome"] = "writer_audio_vacio"
            return
        ev["transcripcion_len"] = len(texto)
        _core(from_phone, role, texto, ev)
    except Exception as exc:  # noqa: BLE001
        print(f"[agenda_writer] handle_voice error: {type(exc).__name__}: {exc}")
        ev["error"] = f"writer_voice: {type(exc).__name__}: {exc}"
        try:
            twilio_client.send_whatsapp(from_phone, "Tuve un problema procesando el audio. Probá de nuevo en un momento.")
        except Exception:  # noqa: BLE001
            pass

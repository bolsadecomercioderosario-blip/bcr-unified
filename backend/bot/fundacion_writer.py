"""
Carga de actividades en la Agenda de la Fundación por WhatsApp.

App independiente de la Agenda de Comunicación/Secretaría: escribe en la tabla
`fundacion_actividades` (vía fundacion.store), NO en `activities`. Comparte sólo
el "caño" del bot (webhook de Twilio + mapeo de número a rol en
BOT_AGENDA_WRITERS). El número de Anaclara se mapea al rol `fundacion`, y el
router del bot desvía esos mensajes acá en vez de a agenda_writer.

Flujo: la responsable manda texto o audio describiendo la actividad → la IA
extrae {fecha, hora, evento, equipo, métrica} → se muestra un resumen y se pide
CONFIRMACIÓN (botones Sí/No) → al confirmar, se guarda.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

from config import BOT_OPENAI_API_KEY, BOT_OPENAI_MODEL
from database import SessionLocal
from bot import agenda_writer, twilio_client
from bot.db_models import BotPendingWrite
from fundacion import store

_ARG = timedelta(hours=3)          # ART = UTC-3
_PENDING_TTL = timedelta(minutes=30)
_STATE_KIND = "fundacion"

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_WELCOME = (
    "¡Hola! 🗓️ Soy el asistente de la *Agenda de la Fundación*.\n\n"
    "Mandame una actividad (texto o audio) con estos 4 datos:\n"
    "📅 *fecha* · 🕒 *hora* · 📝 *qué actividad* · 👥 *quiénes van*\n\n"
    "Por ejemplo:\n"
    "• _20/8 15 hs reunión con Cargill, van Ana y Nico_\n"
    "• _mañana 9 a 12 Agromakers en Tostado, Nico_\n\n"
    "Si te falta alguno te lo pregunto, y antes de guardar te muestro cómo quedó "
    "para que confirmes. ✅"
)


# --- helpers ----------------------------------------------------------------
def _now_art() -> datetime:
    return datetime.utcnow() - _ARG


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.strip()


def _norm_phone(p: str) -> str:
    return agenda_writer._norm_phone(p)  # mismo criterio que el bot


_YES = {"si", "sii", "sisi", "dale", "ok", "oka", "okey", "confirmo", "confirmar",
        "yes", "sip", "va", "vale", "1", "si!", "s:)", "listo"}
_NO = {"no", "nop", "nel", "cancelar", "cancela", "descartar", "borrar", "2", "no!"}


def _is_yes(t: str) -> bool:
    n = _norm(t).strip(" .!¡¿?")
    return n in _YES


def _is_no(t: str) -> bool:
    n = _norm(t).strip(" .!¡¿?")
    return n in _NO


# --- estado pendiente (reusa la tabla genérica bot_pending_write) -----------
def _get_state(from_phone: str) -> Optional[dict]:
    key = _norm_phone(from_phone)
    db = SessionLocal()
    try:
        row = db.query(BotPendingWrite).filter(BotPendingWrite.from_phone == key).first()
        if not row or not row.state:
            return None
        try:
            st = json.loads(row.state)
        except Exception:  # noqa: BLE001
            return None
        if st.get("kind") != _STATE_KIND:
            return None
        at = st.get("at")
        if at:
            try:
                if datetime.utcnow() - datetime.fromisoformat(at) > _PENDING_TTL:
                    _clear_state(from_phone)
                    return None
            except Exception:  # noqa: BLE001
                pass
        return st
    finally:
        db.close()


def _set_state(from_phone: str, draft: dict, phase: str = "confirmando") -> None:
    key = _norm_phone(from_phone)
    payload = json.dumps({"kind": _STATE_KIND, "draft": draft, "phase": phase,
                          "at": datetime.utcnow().isoformat()})
    db = SessionLocal()
    try:
        row = db.query(BotPendingWrite).filter(BotPendingWrite.from_phone == key).first()
        if row:
            row.state = payload
            row.updated_at = datetime.utcnow()
        else:
            db.add(BotPendingWrite(from_phone=key, state=payload, updated_at=datetime.utcnow()))
        db.commit()
    finally:
        db.close()


def _clear_state(from_phone: str) -> None:
    key = _norm_phone(from_phone)
    db = SessionLocal()
    try:
        db.query(BotPendingWrite).filter(BotPendingWrite.from_phone == key).delete()
        db.commit()
    finally:
        db.close()


# --- OpenAI -----------------------------------------------------------------
def _client():
    if not BOT_OPENAI_API_KEY:
        return None
    from openai import OpenAI
    return OpenAI(api_key=BOT_OPENAI_API_KEY, timeout=60.0, max_retries=1)


def _extraer(text: str) -> Optional[dict]:
    c = _client()
    if not c:
        return None
    hoy = _now_art()
    prompt = (
        "Sos un asistente que extrae UNA actividad de agenda a partir de un mensaje "
        "en español rioplatense. Devolvé SOLO un JSON con estas claves:\n"
        '{"fecha":"YYYY-MM-DD","hora":"","evento":"","equipo":"","metricas":""}\n\n'
        f"Hoy es {hoy.strftime('%Y-%m-%d')} ({_MESES[hoy.month-1]} de {hoy.year}). "
        "Resolvé fechas relativas (hoy, mañana, 'el viernes', '20 de agosto') a fecha "
        "absoluta. Si no se menciona el año, asumí el más cercano a futuro. Si no hay "
        "fecha, dejá fecha vacía.\n"
        "IMPORTANTE: completá SÓLO los campos que el mensaje menciona; dejá vacío ('') "
        "todo lo que NO se diga explícitamente. No inventes.\n"
        "- hora: tal como se diga ('15 hs', '9 a 12 hs'). Si dicen que es todo el día o "
        "sin horario fijo, poné 'todo el día'. Vacío si no se menciona.\n"
        "- evento: la descripción/título, SIN la fecha ni la hora adentro.\n"
        "- equipo: quiénes participan. En la Fundación son Anaclara (Ana) y Nicolás (Nico); "
        "'los dos'/'ambos' = 'Ana y Nico'. Puede haber otros nombres. Vacío si no se menciona.\n"
        "- metricas: dato cuantitativo si lo hubiera (ej. '70 estudiantes'); vacío si no.\n\n"
        f"Mensaje: {text}"
    )
    try:
        r = c.responses.create(model=BOT_OPENAI_MODEL, input=prompt)
        raw = (getattr(r, "output_text", "") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[fundacion_writer] LLM falló: {type(exc).__name__}: {exc}")
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        print(f"[fundacion_writer] JSON inválido: {raw!r}")
        return None
    if not isinstance(data, dict):
        return None
    return {k: str(data.get(k) or "").strip() for k in ("fecha", "hora", "evento", "equipo", "metricas")}


# --- presentación -----------------------------------------------------------
def _fecha_larga(iso: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", iso or "")
    if not m:
        return iso or "(sin fecha)"
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return f"{d} de {_MESES[mo-1]} {y}"
    except Exception:  # noqa: BLE001
        return iso


def _resumen(d: dict) -> str:
    lin = [f"📅 {_fecha_larga(d.get('fecha',''))}"]
    if d.get("hora"):
        lin.append(f"🕒 {d['hora']}")
    lin.append(f"📝 {d.get('evento','') or '(sin detalle)'}")
    if d.get("equipo"):
        lin.append(f"👥 {d['equipo']}")
    if d.get("metricas"):
        lin.append(f"📊 {d['metricas']}")
    return "\n".join(lin)


def _send(from_phone: str, msg: str) -> None:
    twilio_client.send_whatsapp(from_phone, msg)


def _send_confirmacion(from_phone: str, draft: dict) -> None:
    full = "Así quedaría la actividad:\n\n" + _resumen(draft)
    try:
        sid = agenda_writer.ensure_confirm_content_sid()
        if sid:
            twilio_client.send_whatsapp_content(from_phone, sid, {"1": full})
            return
    except Exception as exc:  # noqa: BLE001
        print(f"[fundacion_writer] botones fallaron, fallback texto: {exc}")
    _send(from_phone, full + "\n\n¿La *cargo*? Respondé *SÍ* o *NO*.")


# --- completitud de campos --------------------------------------------------
# Obligatorios antes de guardar: fecha, hora, título (evento) y quiénes (equipo).
# 'metricas' es opcional.
_REQUIRED = [("fecha", "la fecha"), ("hora", "la hora"),
             ("evento", "qué actividad es"), ("equipo", "quiénes participan")]


def _faltantes(draft: dict) -> list:
    return [(f, lbl) for f, lbl in _REQUIRED if not (draft.get(f) or "").strip()]


def _merge(viejo: dict, nuevo: dict) -> dict:
    """Combina: toma el dato nuevo si vino, si no conserva el anterior."""
    out = dict(viejo or {})
    for k in ("fecha", "hora", "evento", "equipo", "metricas"):
        v = (nuevo or {}).get(k, "")
        if v and str(v).strip():
            out[k] = str(v).strip()
        else:
            out.setdefault(k, out.get(k, ""))
    return out


def _resumen_parcial(d: dict) -> str:
    lin = []
    if d.get("fecha"):
        lin.append(f"📅 {_fecha_larga(d['fecha'])}")
    if d.get("hora"):
        lin.append(f"🕒 {d['hora']}")
    if d.get("evento"):
        lin.append(f"📝 {d['evento']}")
    if d.get("equipo"):
        lin.append(f"👥 {d['equipo']}")
    if d.get("metricas"):
        lin.append(f"📊 {d['metricas']}")
    return "\n".join(lin)


def _frase_faltantes(falt: list) -> str:
    labels = [lbl for _, lbl in falt]
    if len(labels) == 1:
        return f"Me falta *{labels[0]}*."
    return "Me faltan *" + "*, *".join(labels[:-1]) + f"* y *{labels[-1]}*."


def _pedir_faltantes(from_phone: str, draft: dict, falt: list) -> None:
    parcial = _resumen_parcial(draft)
    msg = "Voy anotando:\n\n" + (parcial + "\n\n" if parcial else "")
    msg += _frase_faltantes(falt) + " ¿Me lo pasás?"
    _send(from_phone, msg)


def _guardar(from_phone: str, draft: dict, ev: dict) -> None:
    db = SessionLocal()
    try:
        store.crear(db, draft, origen="whatsapp", created_by=f"whatsapp:{_norm_phone(from_phone)}")
    finally:
        db.close()
    _clear_state(from_phone)
    ev["outcome"] = "fundacion_guardada"
    _send(from_phone, "✅ ¡Listo! La cargué en la agenda:\n\n" + _resumen(draft))


def _avanzar(from_phone: str, draft: dict, ev: dict) -> None:
    """Pide lo que falte; si está completo, pasa a confirmación."""
    falt = _faltantes(draft)
    if falt:
        _set_state(from_phone, draft, phase="completando")
        ev["outcome"] = "fundacion_faltan"
        _pedir_faltantes(from_phone, draft, falt)
        return
    _set_state(from_phone, draft, phase="confirmando")
    ev["outcome"] = "fundacion_borrador"
    _send_confirmacion(from_phone, draft)


# --- núcleo -----------------------------------------------------------------
def _core(from_phone: str, text: str, ev: dict) -> None:
    text = (text or "").strip()
    if not text:
        return

    state = _get_state(from_phone)
    if state:
        draft = state.get("draft", {})
        phase = state.get("phase", "confirmando")

        if phase == "confirmando":
            if _is_yes(text):
                _guardar(from_phone, draft, ev)
                return
            if _is_no(text):
                _clear_state(from_phone)
                ev["outcome"] = "fundacion_descartada"
                _send(from_phone, "Dale, la descarté. Cuando quieras mandame la actividad de nuevo. 👍")
                return
            # Corrección: re-extraigo y combino con lo que había.
            draft = _merge(draft, _extraer(text) or {})
            _avanzar(from_phone, draft, ev)
            return

        # phase == "completando": espero los datos que faltaban.
        if _is_no(text):
            _clear_state(from_phone)
            ev["outcome"] = "fundacion_descartada"
            _send(from_phone, "Listo, la descarté. Mandámela de nuevo cuando quieras. 👍")
            return
        draft = _merge(draft, _extraer(text) or {})
        _avanzar(from_phone, draft, ev)
        return

    # Sin borrador pendiente.
    if _is_yes(text) or _is_no(text) or len(_norm(text)) <= 2:
        _send(from_phone, _WELCOME)
        return

    draft = _extraer(text)
    if not draft or not any((draft.get(k) or "").strip() for k in ("fecha", "hora", "evento", "equipo")):
        ev["outcome"] = "fundacion_sin_datos"
        _send(from_phone, "Mmm, no pude sacar la actividad de ese mensaje. 🤔\n\n"
                          "Probá algo como: _20/8 15 hs reunión con Cargill, van Ana y Nico_")
        return
    _avanzar(from_phone, draft, ev)


# --- entrypoints (los llama bot/router.py) ----------------------------------
def handle_text(from_phone: str, role: str, text: str, ev: dict) -> None:  # noqa: ARG001
    try:
        _core(from_phone, text, ev)
    except Exception as exc:  # noqa: BLE001
        print(f"[fundacion_writer] handle_text falló: {type(exc).__name__}: {exc}")
        try:
            _send(from_phone, "Tuve un problema procesando el mensaje. Probá de nuevo en un momento.")
        except Exception:  # noqa: BLE001
            pass


def handle_voice(from_phone: str, role: str, media_url: str, media_type: str, ev: dict) -> None:  # noqa: ARG001
    try:
        text = agenda_writer.transcribe(media_url, media_type)
        if not text:
            _send(from_phone, "No pude entender el audio. ¿Lo probás de nuevo, más claro?")
            return
        _core(from_phone, text, ev)
    except Exception as exc:  # noqa: BLE001
        print(f"[fundacion_writer] handle_voice falló: {type(exc).__name__}: {exc}")
        try:
            _send(from_phone, "Tuve un problema procesando el audio. Probá de nuevo en un momento.")
        except Exception:  # noqa: BLE001
            pass

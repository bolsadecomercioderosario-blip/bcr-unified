"""
Cliente mínimo para Twilio WhatsApp.

Sólo dos cosas:
1. verify_signature(): valida que un POST entrante haya sido firmado por
   Twilio con nuestro Auth Token. Sin esto, cualquiera con la URL del
   webhook podría dispararle mensajes al bot y consumir tokens de OpenAI.
2. send_whatsapp(): manda un mensaje saliente vía la REST API de Twilio.

No usamos la lib oficial `twilio` para no sumar una dependencia entera por
dos llamadas. La validación de firma sigue al algoritmo documentado de
Twilio (HMAC-SHA1 sobre URL + params ordenados, base64).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Mapping

import requests
from requests.auth import HTTPBasicAuth

from config import (
    BOT_TWILIO_ACCOUNT_SID,
    BOT_TWILIO_AUTH_TOKEN,
    BOT_TWILIO_WHATSAPP_FROM,
)


_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"
_TWILIO_CONTENT_BASE = "https://content.twilio.com/v1"


class TwilioNotConfigured(RuntimeError):
    """Faltan TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN en el entorno."""


def is_configured() -> bool:
    return bool(BOT_TWILIO_ACCOUNT_SID and BOT_TWILIO_AUTH_TOKEN)


def verify_signature(url: str, params: Mapping[str, str], signature: str) -> bool:
    """Verifica X-Twilio-Signature contra la URL + body form del request.

    Devuelve False si falta el auth token (defensivo — preferimos rechazar a
    aceptar) o si el HMAC no matchea. Comparación constant-time para no
    filtrar info por timing.
    """
    if not BOT_TWILIO_AUTH_TOKEN or not signature:
        return False

    # Algoritmo Twilio: URL + concatenación de cada (param_name + param_value)
    # ordenados alfabéticamente por nombre.
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))

    digest = hmac.new(
        BOT_TWILIO_AUTH_TOKEN.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


# WhatsApp corta los mensajes a ~1600 caracteres; si mandamos más, Twilio
# devuelve 400 y el usuario no recibe nada. Partimos a ~1500 por las dudas.
_WA_MAX = 1500


def _split_message(text: str, limit: int = _WA_MAX) -> list[str]:
    """Parte un texto largo en trozos <= limit, respetando líneas/párrafos."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf = ""
    for line in text.split("\n"):
        # Una sola línea más larga que el límite: la cortamos duro.
        while len(line) > limit:
            if buf:
                parts.append(buf); buf = ""
            parts.append(line[:limit])
            line = line[limit:]
        add = (buf + "\n" + line) if buf else line
        if len(add) > limit:
            parts.append(buf); buf = line
        else:
            buf = add
    if buf:
        parts.append(buf)
    return parts or [""]


def _send_one(to: str, body: str, timeout_s: float) -> dict:
    url = f"{_TWILIO_API_BASE}/Accounts/{BOT_TWILIO_ACCOUNT_SID}/Messages.json"
    response = requests.post(
        url,
        auth=HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN),
        data={"To": to, "From": BOT_TWILIO_WHATSAPP_FROM, "Body": body},
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()


def download_media(url: str, timeout_s: float = 20.0) -> tuple[bytes, str]:
    """Descarga un adjunto (ej. un audio de WhatsApp) desde un MediaUrl de Twilio.
    Los MediaUrl requieren autenticación con el Account SID/Auth Token. Devuelve
    (bytes, content_type)."""
    if not is_configured():
        raise TwilioNotConfigured("TWILIO_ACCOUNT_SID/AUTH_TOKEN no seteados.")
    r = requests.get(
        url,
        auth=HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN),
        timeout=timeout_s,
    )
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "")


def send_whatsapp(to: str, body: str, timeout_s: float = 15.0) -> dict:
    """Manda un mensaje de WhatsApp vía Twilio. Devuelve el JSON del último envío.

    `to` debe venir en formato 'whatsapp:+549...' (Twilio lo requiere así). Si el
    texto excede ~1600 caracteres, se parte en varios mensajes (WhatsApp lo corta
    y Twilio devuelve 400). Si Twilio rechaza, levanta requests.HTTPError.
    """
    if not is_configured():
        raise TwilioNotConfigured(
            "TWILIO_ACCOUNT_SID y/o TWILIO_AUTH_TOKEN no están seteados."
        )
    last: dict = {}
    for part in _split_message(body):
        last = _send_one(to, part, timeout_s)
    return last


# ---------------------------------------------------------------------------
# Menú interactivo (WhatsApp list-picker) — 6 opciones para la Mesa Ejecutiva.
# WhatsApp permite máx. 3 botones de respuesta rápida; con 6 opciones va una
# LISTA (list-picker), que se puede mandar como respuesta dentro de la ventana
# de 24h (no requiere aprobación de Meta). Se manda por ContentSid (Content API).
# Títulos ≤24 chars, descripciones ≤72, botón ≤20 (límites de WhatsApp).
# ---------------------------------------------------------------------------
MENU_SALUDO = ("Hola! Este es el bot de la Bolsa de Comercio de Rosario para los "
               "miembros de la Mesa Ejecutiva. ¿En qué puedo ayudarte?")

_MENU_CONTENT_DEFINITION = {
    "friendly_name": "bcr_menu_mesa",
    "language": "es",
    "types": {
        "twilio/list-picker": {
            "body": MENU_SALUDO,
            "button": "Ver opciones",
            "items": [
                {"id": "agenda", "item": "Agenda de Compromisos", "description": "Actividades de la Mesa Ejecutiva"},
                {"id": "precios", "item": "Precios y mercado", "description": "Pizarra y comentarios diarios"},
                {"id": "informativo", "item": "Informativo Semanal", "description": "Resumen semanal del mercado"},
                {"id": "gea", "item": "Estimaciones y clima", "description": "GEA: cultivos y campaña"},
                {"id": "asuntos", "item": "Asuntos Públicos", "description": "Agenda de asuntos públicos"},
                {"id": "conectados", "item": "Qué hizo la BCR", "description": "Newsletter Conectados"},
            ],
        },
        # Fallback para clientes que no rendericen la lista.
        "twilio/text": {
            "body": MENU_SALUDO + "\n\nOpciones: 1) Agenda de Compromisos · 2) Precios "
            "y mercado · 3) Informativo Semanal · 4) Estimaciones y clima (GEA) · "
            "5) Asuntos Públicos · 6) Qué hizo la BCR (Conectados). Escribime tu consulta.",
        },
    },
}


def create_menu_content_sid() -> str:
    """Crea el Content template del menú (list-picker) vía Content API y devuelve
    su ContentSid (HX...). Se llama una vez; el SID se persiste en bot_config."""
    if not is_configured():
        raise TwilioNotConfigured("TWILIO_ACCOUNT_SID/AUTH_TOKEN no seteados.")
    r = requests.post(
        f"{_TWILIO_CONTENT_BASE}/Content",
        auth=HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN),
        json=_MENU_CONTENT_DEFINITION,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["sid"]


# Botones de confirmación (quick-reply, 2 botones Sí/No). El cuerpo es dinámico
# ({{1}} = resumen de la actividad). Al tocar un botón, WhatsApp manda el `id`
# ("si"/"no") como Body — se procesa igual que si lo hubieran escrito.
_CONFIRM_CONTENT_DEFINITION = {
    "friendly_name": "bcr_confirm_actividad",
    "language": "es",
    "variables": {"1": "resumen de la actividad"},
    "types": {
        "twilio/quick-reply": {
            "body": "{{1}}",
            "actions": [
                {"id": "si", "title": "Sí"},
                {"id": "no", "title": "No"},
            ],
        },
        "twilio/text": {
            "body": "{{1}}\n\nRespondé *SÍ* o *NO*.",
        },
    },
}


def create_confirm_content_sid() -> str:
    """Crea el template de confirmación (quick-reply Sí/No) y devuelve su SID."""
    if not is_configured():
        raise TwilioNotConfigured("TWILIO_ACCOUNT_SID/AUTH_TOKEN no seteados.")
    r = requests.post(
        f"{_TWILIO_CONTENT_BASE}/Content",
        auth=HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN),
        json=_CONFIRM_CONTENT_DEFINITION,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["sid"]


def send_whatsapp_content(to: str, content_sid: str, content_variables: dict | None = None,
                          timeout_s: float = 15.0) -> dict:
    """Manda un mensaje de contenido (template/interactivo) por ContentSid."""
    if not is_configured():
        raise TwilioNotConfigured("TWILIO_ACCOUNT_SID/AUTH_TOKEN no seteados.")
    url = f"{_TWILIO_API_BASE}/Accounts/{BOT_TWILIO_ACCOUNT_SID}/Messages.json"
    data = {"To": to, "From": BOT_TWILIO_WHATSAPP_FROM, "ContentSid": content_sid}
    if content_variables:
        data["ContentVariables"] = json.dumps(content_variables)
    response = requests.post(
        url,
        auth=HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN),
        data=data,
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()


# Respuesta TwiML vacía. Twilio espera XML; con un <Response/> sin Mensaje
# le decimos "ya respondí (o voy a responder) por la REST API, no agregues
# nada vos". Si devolvemos vacío puro, Twilio loguea warning.
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

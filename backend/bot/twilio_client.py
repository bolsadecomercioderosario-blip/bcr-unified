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
from typing import Mapping

import requests
from requests.auth import HTTPBasicAuth

from config import (
    BOT_TWILIO_ACCOUNT_SID,
    BOT_TWILIO_AUTH_TOKEN,
    BOT_TWILIO_WHATSAPP_FROM,
)


_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


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


def send_whatsapp(to: str, body: str, timeout_s: float = 15.0) -> dict:
    """Manda un mensaje de WhatsApp vía Twilio. Devuelve el JSON de respuesta.

    `to` debe venir en formato 'whatsapp:+549...' (Twilio lo requiere así).
    Si Twilio rechaza el request, levanta requests.HTTPError — el caller
    decide si reintentar o degradar.
    """
    if not is_configured():
        raise TwilioNotConfigured(
            "TWILIO_ACCOUNT_SID y/o TWILIO_AUTH_TOKEN no están seteados."
        )

    url = f"{_TWILIO_API_BASE}/Accounts/{BOT_TWILIO_ACCOUNT_SID}/Messages.json"
    response = requests.post(
        url,
        auth=HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN),
        data={
            "To": to,
            "From": BOT_TWILIO_WHATSAPP_FROM,
            "Body": body,
        },
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()


# Respuesta TwiML vacía. Twilio espera XML; con un <Response/> sin Mensaje
# le decimos "ya respondí (o voy a responder) por la REST API, no agregues
# nada vos". Si devolvemos vacío puro, Twilio loguea warning.
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

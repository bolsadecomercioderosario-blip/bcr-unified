"""
Vigía de entradas de Antesala (antesala.com.ar).

Cada 15 minutos (job del scheduler del bot) consulta las ventas de los eventos
configurados en ANTESALA_EVENTOS y, si el total de entradas cambió desde la
última vez, avisa por WhatsApp a los números de ANTESALA_AVISO_A.

Cómo se lee el total
--------------------
El panel de boletería (antesala.com.ar/dashboard/boleteria/<id>) pide a
`api.antesala.com.ar/public/api/reportes?filter[eventos_id]=<id>...` la lista
de compras. Cada compra trae `reporte_codigo`: un código por entrada emitida
(un "Promo 4x3 Pack" son 4 códigos). El "TOTAL DE ENTRADAS" del panel es la
cantidad total de códigos, así que contamos eso.

Autenticación
-------------
Bearer token de sesión (localStorage "token_api" del panel). El login de
Antesala tiene reCAPTCHA, así que NO nos logueamos solos: el token se carga a
mano (env var ANTESALA_TOKEN o POST /api/bot/admin/antesala/token) y dura
72 hs. Si vence (401), avisamos UNA vez por WhatsApp para que se renueve.

WhatsApp fuera de la ventana de 24 hs
-------------------------------------
El número del bot es de empresa: sólo puede mandar texto libre dentro de las
24 hs desde el último mensaje del destinatario. Fuera de esa ventana hace
falta una plantilla aprobada por Meta. Si hay plantilla aprobada
(POST /api/bot/admin/antesala/setup-template la crea y la manda a aprobar),
los avisos de venta van por ella; si no, van como texto libre.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from config import ANTESALA_AVISO_A, ANTESALA_EVENTOS, ANTESALA_TOKEN
from bot import twilio_client
from bot.db_models import BotConfig


_API = "https://api.antesala.com.ar/public/api"
_TIMEOUT_S = 20

# Claves en bot_config (KV persistente, sobrevive restarts de Render).
_K_TOKEN = "antesala_token"
_K_TEMPLATE = "antesala_template_sid"
_K_TOKEN_ALERTADO = "antesala_token_alertado"  # hash del token ya avisado como vencido

# Uso puntual: la función es el sáb 14/11/2026 21:00. El vigía se apaga solo el
# dom 15/11 a las 03:00 ART (06:00 UTC), aunque el código siga desplegado.
_APAGADO_UTC = datetime(2026, 11, 15, 6, 0)


def _k_total(evento_id: str) -> str:
    return f"antesala_total_{evento_id}"


# ---------------------------------------------------------------------------
# Helpers de bot_config
# ---------------------------------------------------------------------------
def _get(db: Session, key: str) -> str | None:
    row = db.query(BotConfig).filter(BotConfig.key == key).first()
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(BotConfig).filter(BotConfig.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        db.add(BotConfig(key=key, value=value))
    db.commit()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def eventos() -> list[str]:
    return [e.strip() for e in ANTESALA_EVENTOS.split(",") if e.strip()]


def destinatarios() -> list[str]:
    out = []
    for n in ANTESALA_AVISO_A.split(","):
        n = n.strip().replace(" ", "")
        if not n:
            continue
        if not n.startswith("whatsapp:"):
            n = "whatsapp:" + (n if n.startswith("+") else "+" + n)
        out.append(n)
    return out


def get_token(db: Session) -> str:
    """El token cargado por endpoint tiene prioridad sobre la env var."""
    return (_get(db, _K_TOKEN) or ANTESALA_TOKEN or "").strip()


def set_token(db: Session, token: str) -> None:
    _set(db, _K_TOKEN, token.strip())


def token_vence(token: str) -> datetime | None:
    """Fecha de vencimiento (UTC) leyendo el claim `exp` del JWT. No verifica
    la firma: sólo sirve para mostrar cuándo hay que renovarlo."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
        return datetime.utcfromtimestamp(int(exp))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Lectura de Antesala
# ---------------------------------------------------------------------------
class TokenVencido(RuntimeError):
    """Antesala respondió 401: el token venció o es inválido."""


def leer_evento(token: str, evento_id: str) -> dict:
    """Devuelve {'nombre', 'total', 'compras'} del evento."""
    r = requests.get(
        f"{_API}/reportes",
        params={
            "filter[eventos_id]": evento_id,
            "filter[status]": "ACTIVO,INVITADO",
            "per_page": 1000,
            "boleteria": 1,
        },
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=_TIMEOUT_S,
    )
    if r.status_code == 401:
        raise TokenVencido("Antesala devolvió 401")
    r.raise_for_status()
    j = r.json()
    if j.get("next_page_url"):
        # per_page=1000 alcanza de sobra para una sala; si algún día no, avisamos
        # en el log en vez de contar de menos en silencio.
        print(f"[antesala] evento {evento_id}: hay más de una página de compras; "
              "el total puede estar incompleto.")
    data = j.get("data") or []
    total = sum(len(c.get("reporte_codigo") or []) for c in data)
    nombre = ""
    for c in data:
        nombre = ((c.get("evento") or {}).get("nombre") or "").strip()
        if nombre:
            break
    return {"nombre": nombre or f"evento {evento_id}", "total": total, "compras": len(data)}


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------
def _enviar_texto(body: str) -> None:
    for to in destinatarios():
        try:
            twilio_client.send_whatsapp(to, body)
        except Exception as exc:  # noqa: BLE001
            print(f"[antesala] falló envío a {to}: {type(exc).__name__}: {exc}")


def _enviar_aviso_venta(db: Session, nombre: str, total: int, delta: int) -> None:
    delta_txt = f"+{delta}" if delta > 0 else str(delta)
    sid = _get(db, _K_TEMPLATE)
    if sid and template_aprobada(sid):
        for to in destinatarios():
            try:
                twilio_client.send_whatsapp_content(
                    to, sid, {"1": nombre, "2": str(total), "3": delta_txt}
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[antesala] falló envío (plantilla) a {to}: {type(exc).__name__}: {exc}")
        return
    _enviar_texto(
        f"🎟️ Novedad en la boletería de *{nombre}*: ya hay *{total}* entradas "
        f"vendidas ({delta_txt} desde el último aviso)."
    )


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------
def revisar(db: Session) -> dict:
    """Una pasada del vigía. Idempotente: sólo avisa si el total cambió."""
    if datetime.utcnow() >= _APAGADO_UTC:
        return {"status": "apagado", "detalle": "terminó el evento"}
    evs = eventos()
    if not evs:
        return {"status": "apagado", "detalle": "ANTESALA_EVENTOS vacío"}
    if not destinatarios():
        return {"status": "apagado", "detalle": "ANTESALA_AVISO_A vacío"}
    token = get_token(db)
    if not token:
        return {"status": "sin_token"}

    resultados = []
    for ev in evs:
        try:
            info = leer_evento(token, ev)
        except TokenVencido:
            h = hashlib.sha256(token.encode()).hexdigest()[:16]
            if _get(db, _K_TOKEN_ALERTADO) != h:
                _enviar_texto(
                    "⚠️ Se venció la sesión de Antesala del vigía de entradas. "
                    "Entrá a antesala.com.ar y renová el token para seguir recibiendo avisos."
                )
                _set(db, _K_TOKEN_ALERTADO, h)
            return {"status": "token_vencido"}
        except Exception as exc:  # noqa: BLE001
            resultados.append({"evento": ev, "error": f"{type(exc).__name__}: {exc}"})
            continue

        previo_raw = _get(db, _k_total(ev))
        total = info["total"]
        if previo_raw is None:
            # Primera pasada: guardamos la línea de base y confirmamos que anda.
            _set(db, _k_total(ev), str(total))
            _enviar_texto(
                f"👀 Vigía de entradas activado para *{info['nombre']}*. "
                f"Total actual: *{total}* entradas. Te aviso cuando cambie."
            )
            resultados.append({"evento": ev, "total": total, "aviso": "inicial"})
            continue

        previo = int(previo_raw)
        if total != previo:
            _enviar_aviso_venta(db, info["nombre"], total, total - previo)
            _set(db, _k_total(ev), str(total))
            resultados.append({"evento": ev, "total": total, "previo": previo, "aviso": True})
        else:
            resultados.append({"evento": ev, "total": total, "aviso": False})

    return {"status": "ok", "eventos": resultados}


def estado(db: Session) -> dict:
    token = get_token(db)
    vence = token_vence(token) if token else None
    sid = _get(db, _K_TEMPLATE)
    return {
        "eventos": {ev: _get(db, _k_total(ev)) for ev in eventos()},
        "destinatarios": len(destinatarios()),
        "token_cargado": bool(token),
        "token_origen": "db" if _get(db, _K_TOKEN) else ("env" if ANTESALA_TOKEN else None),
        "token_vence_utc": vence.isoformat() if vence else None,
        "plantilla_sid": sid,
        "plantilla_estado": template_estado(sid) if sid else None,
    }


# ---------------------------------------------------------------------------
# Plantilla de WhatsApp (para avisar fuera de la ventana de 24 hs)
# ---------------------------------------------------------------------------
_TEMPLATE_NAME = "antesala_ventas"
_TEMPLATE_DEFINITION = {
    "friendly_name": _TEMPLATE_NAME,
    "language": "es",
    "variables": {"1": "El más acá", "2": "56", "3": "+3"},
    "types": {
        "twilio/text": {
            "body": "🎟️ Novedad en la boletería de {{1}}: ya hay {{2}} entradas "
                    "vendidas ({{3}} desde el último aviso).",
        },
    },
}


def _content_auth():
    from requests.auth import HTTPBasicAuth
    from config import BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN
    return HTTPBasicAuth(BOT_TWILIO_ACCOUNT_SID, BOT_TWILIO_AUTH_TOKEN)


def crear_template(db: Session) -> dict:
    """Crea la plantilla en Twilio Content API y la manda a aprobar a WhatsApp
    como UTILITY. Guarda el SID en bot_config."""
    if not twilio_client.is_configured():
        raise twilio_client.TwilioNotConfigured("Twilio no configurado.")
    base = "https://content.twilio.com/v1/Content"
    r = requests.post(base, auth=_content_auth(), json=_TEMPLATE_DEFINITION, timeout=20)
    r.raise_for_status()
    sid = r.json()["sid"]
    _set(db, _K_TEMPLATE, sid)
    a = requests.post(
        f"{base}/{sid}/ApprovalRequests/whatsapp",
        auth=_content_auth(),
        json={"name": _TEMPLATE_NAME, "category": "UTILITY"},
        timeout=20,
    )
    a.raise_for_status()
    return {"sid": sid, "aprobacion": a.json().get("status")}


def template_estado(sid: str) -> str | None:
    """Estado de aprobación de WhatsApp: received / pending / approved / rejected."""
    try:
        r = requests.get(
            f"https://content.twilio.com/v1/Content/{sid}/ApprovalRequests",
            auth=_content_auth(),
            timeout=15,
        )
        r.raise_for_status()
        return ((r.json().get("whatsapp") or {}).get("status")) or None
    except Exception as exc:  # noqa: BLE001
        return f"error: {type(exc).__name__}"


def template_aprobada(sid: str) -> bool:
    return template_estado(sid) == "approved"

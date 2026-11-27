"""
Vigía de ventas de EventoSimple (app.evento-simple.com).

Monitorea cuántas entradas lleva vendidas un evento del panel del organizador
y avisa por WhatsApp cuando hay ventas NUEVAS. Es de solo lectura: lee una API
interna del panel (`lotes-stats`), no hace ninguna acción sobre el evento.

Pensado para un único evento en venta a la vez (hoy: "NOCHE DE MURGA: Y PARIÓ
LA ABUELA + CONTRAFLOR (CÓRDOBA)", cuenta 78 / evento 362). Todo configurable
por env var en Render — ver config.py (EVENTOSIMPLE_*).

Autenticación — el punto delicado
----------------------------------
EventoSimple usa dos tokens:
  - token de ACCESO: vida ~15 min, se manda en el header `token-acceso` para
    leer datos. Se invalida apenas se emite uno nuevo (de un solo uso).
  - token de ACTUALIZACIÓN (refresh): vida ~30 días, se manda en el header
    `token-actualizacion` a POST /auth/cliente/renovartokens para obtener un
    ACCESO nuevo. OJO: **también rota en cada renovación** (el refresh viejo
    muere y la respuesta trae uno nuevo).

Por eso cada ciclo:
  1. renovar con el refresh ACTUAL → obtener acceso nuevo + refresh nuevo.
  2. persistir el refresh nuevo YA (si no, un restart de Render lo pierde).
  3. leer lotes-stats con el acceso nuevo.

Y por eso el vigía necesita una **sesión dedicada**: si otra persona (o la app
web) se loguea con la misma cuenta y renueva, le pisa el refresh al vigía y se
corta la cadena. Cuando eso pasa, renovar da 401 → avisamos UNA vez y marcamos
`desconectado` hasta que se re-bootstrapee con un token fresco.

Bootstrap: se captura el refresh inicial logueándose una vez en
app.evento-simple.com y copiando `localStorage.sesionfl_actualizacion.token`.
Va en EVENTOSIMPLE_REFRESH_TOKEN (semilla); de ahí en más el vigía persiste el
token rotado en la DB (tabla eventosimple_vigia_state).
"""
from __future__ import annotations

from datetime import datetime

import requests
from sqlalchemy.orm import Session

import config
from bot import db_models
from bot import twilio_client


_API_BASE = "https://api.evento-simple.com/v1.0"
_TIMEOUT = 20.0


class _ChainRota(RuntimeError):
    """El refresh token no sirve (401): alguien rotó la cadena o venció."""


def _renovar(refresh_token: str, cuenta: str) -> tuple[str, str]:
    """POST /auth/cliente/renovartokens. Devuelve (acceso_nuevo, refresh_nuevo).

    Levanta _ChainRota si el refresh fue rechazado (401), o requests.HTTPError
    para otros errores HTTP.
    """
    r = requests.post(
        f"{_API_BASE}/auth/cliente/renovartokens",
        headers={"content-type": "application/json",
                 "token-actualizacion": refresh_token},
        json={"idProductor": int(cuenta)},
        timeout=_TIMEOUT,
    )
    if r.status_code in (401, 403):
        raise _ChainRota(f"renovartokens devolvió {r.status_code}")
    r.raise_for_status()
    j = r.json()
    datos = j.get("datos") or j
    acceso = (datos.get("acceso") or {}).get("token")
    refresh = (datos.get("actualizacion") or {}).get("token")
    if not acceso or not refresh:
        raise RuntimeError(f"renovartokens sin tokens en la respuesta: {j.get('estado')}")
    return acceso, refresh


def _lotes_stats(cuenta: str, evento: str, acceso: str) -> dict:
    """GET lotes-stats. Devuelve el dict `datos` (ticketsVendidos, etc.)."""
    r = requests.get(
        f"{_API_BASE}/cuentas/{cuenta}/eventos/{evento}/lotes-stats",
        params={"todos": "true", "cache": "false"},
        headers={"content-type": "application/json", "token-acceso": acceso},
        timeout=_TIMEOUT,
    )
    if r.status_code in (401, 403):
        raise _ChainRota(f"lotes-stats devolvió {r.status_code}")
    r.raise_for_status()
    datos = r.json().get("datos") or {}
    if "ticketsVendidos" not in datos:
        raise RuntimeError("lotes-stats sin ticketsVendidos")
    return datos


def _destinatarios() -> list[str]:
    """Números a avisar en formato Twilio ('whatsapp:+549...')."""
    out = []
    for raw in (config.EVENTOSIMPLE_AVISO_A or "").split(","):
        num = raw.strip()
        if not num:
            continue
        if not num.startswith("whatsapp:"):
            num = "whatsapp:" + num
        out.append(num)
    return out


def _avisar(body: str) -> None:
    """Manda un WhatsApp a cada destinatario. No rompe si Twilio falla (ej.
    ventana de 24h vencida): loguea y sigue."""
    for to in _destinatarios():
        try:
            twilio_client.send_whatsapp(to, body)
            print(f"[eventosimple_vigia] aviso -> {to}")
        except Exception as exc:  # noqa: BLE001
            print(f"[eventosimple_vigia] no se pudo avisar a {to}: "
                  f"{type(exc).__name__}: {exc}")


def revisar(db: Session) -> dict:
    """Un ciclo del vigía. Renueva token, lee ventas, compara con lo último
    visto y avisa si hubo ventas nuevas. Devuelve un dict para loguear.

    Idempotente y defensivo: cualquier error se captura y se refleja en el
    dict (el scheduler nunca debe caerse por esto)."""
    if not config.EVENTOSIMPLE_VIGIA_ENABLED:
        return {"status": "desactivado"}
    cuenta = config.EVENTOSIMPLE_CUENTA
    evento = config.EVENTOSIMPLE_EVENTO
    if not (cuenta and evento and _destinatarios()):
        return {"status": "sin_config"}

    state = db.get(db_models.EventoSimpleVigiaState, evento)
    if state is None:
        state = db_models.EventoSimpleVigiaState(evento_id=evento)
        db.add(state)

    refresh = state.refresh_token or config.EVENTOSIMPLE_REFRESH_TOKEN
    if not refresh:
        return {"status": "sin_token"}

    # 1+2) renovar y persistir el refresh nuevo YA.
    try:
        acceso, refresh_nuevo = _renovar(refresh, cuenta)
    except _ChainRota:
        # La cadena se cortó (otra sesión renovó, o venció). Avisar UNA vez.
        if not state.desconectado:
            state.desconectado = True
            state.actualizado_at = datetime.utcnow()
            db.commit()
            _avisar("⚠️ El vigía de entradas perdió la sesión de EventoSimple "
                    "(alguien se logueó con la misma cuenta, o venció el token). "
                    "Hay que re-loguearse y cargar un token nuevo para que vuelva "
                    "a andar.")
        return {"status": "desconectado"}
    except Exception as exc:  # noqa: BLE001 — error transitorio de red/HTTP
        print(f"[eventosimple_vigia] renovar falló (transitorio): "
              f"{type(exc).__name__}: {exc}")
        return {"status": "error_renovar", "error": str(exc)}

    state.refresh_token = refresh_nuevo
    reconectado = state.desconectado
    state.desconectado = False
    db.commit()

    # 3) leer ventas.
    try:
        datos = _lotes_stats(cuenta, evento, acceso)
    except Exception as exc:  # noqa: BLE001
        print(f"[eventosimple_vigia] lotes-stats falló: {type(exc).__name__}: {exc}")
        state.actualizado_at = datetime.utcnow()
        db.commit()
        return {"status": "error_stats", "error": str(exc)}

    vendidos = int(datos.get("ticketsVendidos") or 0)
    total = int(datos.get("ticketsTotal") or 0)
    disponibles = int(datos.get("ticketsDisponibles") or 0)
    previo = state.ultimo_vendidos

    # 4) comparar y avisar.
    if previo is None:
        _avisar(f"✅ Vigía de entradas activo.\n\n"
                f"Evento: {datos.get('estado', 'En venta')}.\n"
                f"Ahora: *{vendidos}* vendidas de {total} ({disponibles} disponibles).\n\n"
                f"Te aviso cuando haya ventas nuevas.")
    elif reconectado:
        _avisar(f"✅ El vigía volvió a conectarse.\n"
                f"Estado actual: *{vendidos}* vendidas de {total}.")
    elif vendidos > previo:
        nuevas = vendidos - previo
        _avisar(f"🎟️ ¡Ventas nuevas! +{nuevas} "
                f"entrada{'s' if nuevas != 1 else ''}.\n\n"
                f"Total: *{vendidos}* vendidas de {total} "
                f"({disponibles} disponibles).")
    # vendidos < previo (devoluciones/anulaciones): actualizamos sin avisar.

    state.ultimo_vendidos = vendidos
    state.ultimo_total = total
    state.actualizado_at = datetime.utcnow()
    db.commit()

    return {"status": "ok", "vendidos": vendidos, "total": total,
            "previo": previo, "nuevas": max(0, vendidos - (previo or vendidos))}

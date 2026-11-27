"""
Vigía de ventas de EventoSimple (app.evento-simple.com).

Monitorea cuántas entradas lleva vendidas un evento del panel del organizador y
avisa por WhatsApp cuando hay ventas NUEVAS. Es de solo lectura: lee una API
interna del panel (`lotes-stats`), no hace ninguna acción sobre el evento.

Pensado para un único evento en venta a la vez (hoy: "NOCHE DE MURGA: Y PARIÓ
LA ABUELA + CONTRAFLOR (CÓRDOBA)", cuenta 78 / evento 362). Todo configurable
por env var en Render — ver config.py (EVENTOSIMPLE_*).

Autenticación — por qué se loguea solo
---------------------------------------
La API de EventoSimple exige una COOKIE de sesión HttpOnly (además del token de
acceso). Esa cookie no se puede extraer ni mantener desde afuera, así que el
vigía hace el login completo él mismo en cada ciclo (como el navegador) y usa
una requests.Session que guarda la cookie para la lectura. Flujo:

  1. POST auth/cliente/identificar {idProductor, usuario}  -> resuelve el id
     numérico del usuario a partir del nombre de usuario.
  2. POST auth/cliente/iniciarsesion {idProductor, usuario:id, contrasena}
     -> devuelve el token de acceso Y setea la cookie en la Session.
  3. GET  cuentas/{cuenta}/eventos/{evento}/lotes-stats  con header Token-Acceso
     (+ la cookie de la Session) -> datos.ticketsVendidos.

Como loguea de cero cada vez, es auto-recuperable: no hay tokens ni cookies que
persistir. Solo guardamos en DB el último conteo visto (para avisar únicamente
cuando sube). Las credenciales van por env var en Render.
"""
from __future__ import annotations

from datetime import datetime

import requests
from sqlalchemy.orm import Session

import config
from bot import db_models
from bot import twilio_client


_API = "https://api.evento-simple.com/v1.0"
_TIMEOUT = 20.0


class _LoginError(RuntimeError):
    """El login fue rechazado (credenciales mal, usuario inexistente, etc.)."""


def _login(cuenta: str, usuario: str, contrasena: str) -> tuple[requests.Session, str]:
    """Loguea en EventoSimple. Devuelve (session, token_acceso). La cookie de
    sesión queda guardada en session.cookies para las lecturas siguientes.

    Levanta _LoginError si las credenciales no sirven; requests.HTTPError /
    RequestException ante errores transitorios de red/HTTP.
    """
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    # 1) resolver el id numérico del usuario a partir del nombre de usuario.
    r = s.post(f"{_API}/auth/cliente/identificar",
               json={"idProductor": int(cuenta), "usuario": usuario},
               timeout=_TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if (j.get("estado") or {}).get("resultado") != 1:
        raise _LoginError(f"identificar: {(j.get('estado') or {}).get('mensaje')}")
    usuario_id = (j.get("datos") or {}).get("id")
    if not usuario_id:
        raise _LoginError("identificar no devolvió id de usuario")

    # 2) iniciar sesión (setea la cookie en session.cookies).
    r = s.post(f"{_API}/auth/cliente/iniciarsesion",
               json={"idProductor": int(cuenta), "usuario": usuario_id,
                     "contrasena": contrasena},
               timeout=_TIMEOUT)
    if r.status_code in (401, 403):
        raise _LoginError(f"iniciarsesion rechazado ({r.status_code}) — "
                          "¿cambió la contraseña?")
    r.raise_for_status()
    j = r.json()
    if (j.get("estado") or {}).get("resultado") != 1:
        raise _LoginError(f"iniciarsesion: {(j.get('estado') or {}).get('mensaje')}")
    acceso = ((((j.get("datos") or {}).get("sesion") or {}).get("acceso")) or {}).get("token")
    if not acceso:
        raise _LoginError("iniciarsesion no devolvió token de acceso")
    return s, acceso


def _lotes_stats(s: requests.Session, cuenta: str, evento: str, acceso: str) -> dict:
    """GET lotes-stats (con la cookie de la Session + Token-Acceso). Devuelve el
    dict `datos` (ticketsVendidos, ticketsTotal, ...)."""
    r = s.get(f"{_API}/cuentas/{cuenta}/eventos/{evento}/lotes-stats",
              params={"todos": "true"},
              headers={"Token-Acceso": acceso},
              timeout=_TIMEOUT)
    r.raise_for_status()
    datos = (r.json() or {}).get("datos") or {}
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
    """Un ciclo del vigía: loguea, lee ventas, compara con lo último visto y
    avisa si hubo ventas nuevas. Devuelve un dict para loguear. Defensivo:
    cualquier error se captura (el scheduler nunca debe caerse por esto)."""
    if not config.EVENTOSIMPLE_VIGIA_ENABLED:
        return {"status": "desactivado"}
    cuenta = config.EVENTOSIMPLE_CUENTA
    evento = config.EVENTOSIMPLE_EVENTO
    usuario = config.EVENTOSIMPLE_USUARIO
    contrasena = config.EVENTOSIMPLE_CONTRASENA
    if not (cuenta and evento and usuario and contrasena and _destinatarios()):
        return {"status": "sin_config"}

    state = db.get(db_models.EventoSimpleVigiaState, evento)
    if state is None:
        state = db_models.EventoSimpleVigiaState(evento_id=evento)
        db.add(state)

    # 1+2) login.
    try:
        session, acceso = _login(cuenta, usuario, contrasena)
    except _LoginError as exc:
        # Credenciales rechazadas: avisar UNA vez y esperar a que se corrija.
        if not state.desconectado:
            state.desconectado = True
            state.actualizado_at = datetime.utcnow()
            db.commit()
            _avisar("⚠️ El vigía no pudo entrar a EventoSimple "
                    f"({exc}). Revisá usuario/contraseña en Render.")
        return {"status": "login_fallido", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — transitorio de red/HTTP
        print(f"[eventosimple_vigia] login falló (transitorio): "
              f"{type(exc).__name__}: {exc}")
        return {"status": "error_login", "error": str(exc)}

    reconectado = state.desconectado
    state.desconectado = False

    # 3) leer ventas.
    try:
        datos = _lotes_stats(session, cuenta, evento, acceso)
    except Exception as exc:  # noqa: BLE001
        print(f"[eventosimple_vigia] lotes-stats falló: {type(exc).__name__}: {exc}")
        state.actualizado_at = datetime.utcnow()
        db.commit()
        return {"status": "error_stats", "error": str(exc)}
    finally:
        session.close()

    vendidos = int(datos.get("ticketsVendidos") or 0)
    total = int(datos.get("ticketsTotal") or 0)
    disponibles = int(datos.get("ticketsDisponibles") or 0)
    previo = state.ultimo_vendidos

    # 4) comparar y avisar.
    if previo is None:
        _avisar(f"✅ Vigía de entradas activo.\n\n"
                f"Estado: {datos.get('estado', 'En venta')}.\n"
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

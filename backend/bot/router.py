"""
Módulo Bot BCR: agente conversacional con tools.

Tools enchufadas:
  - consultar_agenda (chunk 2.2) — lee tabla activities
  - buscar_institucional / buscar_informativo / buscar_comentario_diario /
    buscar_informe_gea (chunks 2.3 + GEA) — file_search sobre vector stores OpenAI
  - get_precios_pizarra / get_estimaciones_gea (chunk 2.4 + GEA) — placeholders
    hasta que los scrapers del chunk 3.x los llenen

Endpoints:
  - /api/bot/test — para probar desde el browser (requiere auth bearer)
  - /api/bot/twilio-webhook — público (firmado por Twilio); recibe WhatsApp
  - /api/bot/admin/exchanges — lista los últimos exchanges (debug)
"""
from __future__ import annotations

import traceback
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db

from bot import agent, db_models, models, twilio_client


# /api/bot/test y /admin/* requieren bearer auth (consistente con el resto
# del API). /twilio-webhook se valida con X-Twilio-Signature en el endpoint
# mismo, así que NO va por require_auth.
router = APIRouter(prefix="/api/bot")


# ---------------------------------------------------------------------------
# Endpoint de testing local (browser/curl).
# ---------------------------------------------------------------------------
@router.post(
    "/test",
    response_model=models.BotTestResponse,
    dependencies=[Depends(require_auth)],
)
def bot_test(
    payload: models.BotTestRequest,
    db: Session = Depends(get_db),
) -> models.BotTestResponse:
    """Endpoint manual para probar el bot desde el browser sin pasar por Twilio."""
    try:
        result = agent.run_agent(
            message=payload.message,
            from_phone=payload.from_phone,
            db=db,
            previous_response_id=payload.previous_response_id,
        )
        return models.BotTestResponse(
            reply=result.reply,
            tools_used=result.tools_used,
            response_id=result.response_id,
            debug={"iterations": result.iterations, **result.debug},
        )
    except Exception as exc:  # noqa: BLE001 — bring-up: queremos el error legible
        tb = traceback.format_exc()
        print(f"[bot.test] ERROR procesando mensaje {payload.message!r}: {exc}\n{tb}")
        return models.BotTestResponse(
            reply=f"Se cayó el bot procesando tu mensaje. Detalle: {type(exc).__name__}: {exc}",
            tools_used=[],
            response_id=None,
            debug={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback_tail": tb.splitlines()[-6:],
            },
        )


# ---------------------------------------------------------------------------
# Webhook de Twilio WhatsApp (público, validado por firma).
# ---------------------------------------------------------------------------
def _get_or_create_session(db: Session, from_phone: str) -> tuple[db_models.BotSession, Optional[str]]:
    """Recupera la sesión del usuario; devuelve (session, previous_response_id_aplicable).

    Si la última actividad pasó el TTL, ignoramos el previous_response_id y
    arrancamos conversación nueva.
    """
    session = db.query(db_models.BotSession).filter(
        db_models.BotSession.from_phone == from_phone
    ).first()

    if session is None:
        session = db_models.BotSession(from_phone=from_phone, last_response_id=None)
        db.add(session)
        return session, None

    age = (datetime.utcnow() - session.last_message_at).total_seconds()
    if age > db_models.SESSION_TTL_SECONDS:
        # Sesión expirada — reseteamos memoria.
        session.last_response_id = None
        return session, None

    return session, session.last_response_id


@router.post("/twilio-webhook", include_in_schema=False)
async def twilio_webhook(request: Request, db: Session = Depends(get_db)) -> Response:
    """Recibe un POST de Twilio cuando llega un WhatsApp. Devuelve TwiML vacío
    y dispara la respuesta saliente vía REST API (más confiable que TwiML
    para mensajes largos o que pueden tardar)."""
    form = await request.form()
    params = {k: str(form[k]) for k in form.keys()}

    # Validación de firma — sin esto cualquiera con la URL podría hacernos
    # gastar tokens de OpenAI.
    signature = request.headers.get("X-Twilio-Signature", "")
    # Twilio firma sobre la URL pública. Si la app está detrás de un proxy/
    # CDN (Render lo está), str(request.url) puede no coincidir. Como
    # fallback, leemos un override opcional del header X-Forwarded-Url.
    url = request.headers.get("X-Forwarded-Url") or str(request.url)

    if not twilio_client.verify_signature(url, params, signature):
        print(f"[bot.twilio-webhook] Firma inválida; rechazando. url={url}")
        return Response(status_code=403)

    from_phone = params.get("From", "").strip()
    body = (params.get("Body") or "").strip()

    if not from_phone or not body:
        # Mensaje sin texto (media, sticker, etc.) — respondemos amable.
        if from_phone and twilio_client.is_configured():
            try:
                twilio_client.send_whatsapp(
                    to=from_phone,
                    body="Por ahora sólo entiendo mensajes de texto. ¿Me lo escribís?",
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[bot.twilio-webhook] Falló mandar respuesta no-text: {exc}")
        return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")

    # Recuperamos memoria conversacional (o creamos sesión).
    session, previous_response_id = _get_or_create_session(db, from_phone)

    exchange = db_models.BotExchange(
        from_phone=from_phone,
        message=body,
        reply="",  # lo completamos al final
    )
    db.add(exchange)

    try:
        result = agent.run_agent(
            message=body,
            from_phone=from_phone,
            db=db,
            previous_response_id=previous_response_id,
        )
        reply_text = result.reply
        exchange.reply = reply_text
        exchange.response_id = result.response_id
        exchange.tools_used = list(result.tools_used)
        exchange.iterations = result.iterations
        exchange.success = True

        # Actualizamos memoria conversacional.
        session.last_response_id = result.response_id
        session.last_message_at = datetime.utcnow()

    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        print(f"[bot.twilio-webhook] Agente falló: {exc}\n{tb}")
        reply_text = (
            "Disculpá, tuve un problema procesando tu consulta. Intentá de nuevo "
            "en un momento."
        )
        exchange.reply = reply_text
        exchange.success = False
        exchange.error = f"{type(exc).__name__}: {exc}"

    db.commit()

    # Mandamos la respuesta saliente vía Twilio REST. Si falla, queda el
    # exchange logueado pero el usuario no recibe nada — peor el silencio
    # que tirar 500 a Twilio (que reintentaría disparando duplicados).
    try:
        twilio_client.send_whatsapp(to=from_phone, body=reply_text)
    except twilio_client.TwilioNotConfigured:
        print("[bot.twilio-webhook] Twilio no configurado; no se mandó respuesta.")
    except Exception as exc:  # noqa: BLE001
        print(f"[bot.twilio-webhook] Falló envío Twilio: {exc}")

    return Response(twilio_client.EMPTY_TWIML, media_type="application/xml")


# ---------------------------------------------------------------------------
# Admin: ver los últimos exchanges (debug).
# ---------------------------------------------------------------------------
@router.get(
    "/admin/exchanges",
    dependencies=[Depends(require_auth)],
)
def list_recent_exchanges(
    limit: int = 50,
    from_phone: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Devuelve los últimos N exchanges del log. Útil para ver qué le están
    preguntando al bot y qué responde, sin entrar a la DB a mano."""
    limit = max(1, min(limit, 200))
    q = db.query(db_models.BotExchange)
    if from_phone:
        q = q.filter(db_models.BotExchange.from_phone == from_phone)
    rows = q.order_by(db_models.BotExchange.created_at.desc()).limit(limit).all()

    return {
        "total": len(rows),
        "items": [
            {
                "id": r.id,
                "from_phone": r.from_phone,
                "message": r.message,
                "reply": r.reply,
                "tools_used": r.tools_used or [],
                "iterations": r.iterations,
                "success": r.success,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get(
    "/admin/health",
    dependencies=[Depends(require_auth)],
)
def health_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Diagnóstico rápido — qué hay configurado y qué no."""
    from config import (
        BOT_OPENAI_API_KEY,
        BOT_OPENAI_MODEL,
        BOT_VS_COMENTARIOS,
        BOT_VS_GEA,
        BOT_VS_INFORMATIVO,
        BOT_VS_INSTITUCIONAL,
    )

    yesterday = datetime.utcnow() - timedelta(hours=24)
    recent_count = db.query(db_models.BotExchange).filter(
        db_models.BotExchange.created_at >= yesterday
    ).count()
    failures_24h = db.query(db_models.BotExchange).filter(
        db_models.BotExchange.created_at >= yesterday,
        db_models.BotExchange.success.is_(False),
    ).count()

    return {
        "openai_configured": bool(BOT_OPENAI_API_KEY),
        "openai_model": BOT_OPENAI_MODEL,
        "twilio_configured": twilio_client.is_configured(),
        "vector_stores": {
            "institucional": bool(BOT_VS_INSTITUCIONAL),
            "informativo": bool(BOT_VS_INFORMATIVO),
            "comentarios": bool(BOT_VS_COMENTARIOS),
            "gea": bool(BOT_VS_GEA),
        },
        "exchanges_24h": recent_count,
        "failures_24h": failures_24h,
    }

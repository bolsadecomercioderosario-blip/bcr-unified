"""
Módulo Bot BCR: agente conversacional con tools.

Tools enchufadas:
  - consultar_agenda (chunk 2.2) — lee tabla activities
  - buscar_institucional / buscar_informativo / buscar_comentario_diario
    (chunk 2.3) — file_search sobre vector stores OpenAI

Próximos chunks:
  - 2.4: tool get_precios_pizarra (lee tabla precios_pizarra)
  - 2.5: webhook de Twilio + envío de respuestas + log de exchanges en DB
"""
import traceback

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import require_auth
from database import get_db

from bot import agent, models


router = APIRouter(prefix="/api/bot", dependencies=[Depends(require_auth)])


@router.post("/test", response_model=models.BotTestResponse)
def bot_test(
    payload: models.BotTestRequest,
    db: Session = Depends(get_db),
) -> models.BotTestResponse:
    """Recibe un mensaje y devuelve la respuesta generada por el agente.

    Cualquier excepción del agente (OpenAI down, tool con bug, etc.) se
    captura acá y devolvemos un BotTestResponse con `debug.error` lleno,
    en vez de propagarla como 500 — así la UI muestra el mensaje sin
    perderlo en un Internal Server Error genérico. Crítico mientras el
    bot está en desarrollo; lo podemos endurecer después.
    """
    try:
        result = agent.run_agent(
            message=payload.message,
            from_phone=payload.from_phone,
            db=db,
        )
        return models.BotTestResponse(
            reply=result.reply,
            tools_used=result.tools_used,
            debug={
                "iterations": result.iterations,
                **result.debug,
            },
        )
    except Exception as exc:  # noqa: BLE001 — durante el bring-up queremos ver todo error en la UI
        tb = traceback.format_exc()
        print(f"[bot.test] ERROR procesando mensaje {payload.message!r}: {exc}\n{tb}")
        return models.BotTestResponse(
            reply=f"Se cayó el bot procesando tu mensaje. Detalle: {type(exc).__name__}: {exc}",
            tools_used=[],
            debug={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "traceback_tail": tb.splitlines()[-6:],
            },
        )

"""
Módulo Bot BCR: agente conversacional con tools.

Estado actual (chunk 2.2): el endpoint /api/bot/test ya llama al agente real
con OpenAI + tool calling. La única tool disponible por ahora es
consultar_agenda. Próximos chunks:
  - 2.3: tools RAG sobre vector stores OpenAI (institucional + comentarios + informativo)
  - 2.4: tool get_precios_pizarra (lee tabla precios_pizarra)
  - 2.5: webhook de Twilio + envío de respuestas + log de exchanges en DB
"""
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

    Sirve para testear desde curl o desde un cliente HTTP sin pasar por
    Twilio. Una vez integrado el webhook de WhatsApp (chunk 2.5), el flujo
    público va a usar el mismo agente por debajo.
    """
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

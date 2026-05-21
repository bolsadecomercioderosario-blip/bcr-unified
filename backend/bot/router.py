"""
Módulo Bot BCR: agente conversacional con tools.

Estado actual (chunk 2.1): solo el endpoint de testing local con respuesta
hardcoded. En los próximos chunks iremos sumando:
  - 2.2: tool consultar_agenda (lee tabla activities)
  - 2.3: tools RAG sobre vector stores OpenAI (institucional + comentarios + informativo)
  - 2.4: tool get_precios_pizarra (lee tabla precios_pizarra)
  - 2.5: webhook de Twilio + envío de respuestas + log de exchanges en DB
"""
from fastapi import APIRouter, Depends

from auth import require_auth

from bot import models


router = APIRouter(prefix="/api/bot", dependencies=[Depends(require_auth)])


@router.post("/test", response_model=models.BotTestResponse)
def bot_test(payload: models.BotTestRequest) -> models.BotTestResponse:
    """Endpoint de testing local — recibe un mensaje y devuelve una respuesta.

    Por ahora devuelve un eco hardcoded. En los próximos chunks reemplazamos
    el cuerpo por una llamada al LLM con tools.
    """
    return models.BotTestResponse(
        reply=(
            "Bot BCR (stub chunk 2.1). Recibí tu mensaje y todavía no sé responder, "
            f"pero el endpoint está vivo. Mensaje recibido: {payload.message!r}"
        ),
        tools_used=[],
        debug={
            "stub": True,
            "chunk": "2.1",
            "from_phone": payload.from_phone,
        },
    )

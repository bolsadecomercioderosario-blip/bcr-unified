"""
Modelos del bot BCR.

Pydantic schemas para el endpoint de testing local del bot. Los modelos
SQLAlchemy de logueo (bot_exchanges) se agregarán recién cuando enchufemos
Twilio (chunk 2.5).
"""
from typing import Optional

from pydantic import BaseModel, Field


class BotTestRequest(BaseModel):
    """Input del endpoint POST /bot/test — simula un mensaje entrante.

    `from_phone` permite probar comportamiento dependiente del usuario (ej.
    contexto conversacional cuando lo agreguemos). Es opcional para que un
    `curl` rápido sin payload completo igual funcione.

    `previous_response_id` encadena turnos para que el bot recuerde el
    contexto. La página de prueba lo guarda en memoria y lo manda en cada
    request siguiente; cuando llegue Twilio (2.5), persistiremos esto en
    DB por número de WhatsApp.
    """
    message: str = Field(..., min_length=1, description="Texto que mandaría el usuario por WhatsApp")
    from_phone: Optional[str] = Field(default=None, description="Número del remitente, formato whatsapp:+549...")
    previous_response_id: Optional[str] = Field(
        default=None,
        description="ID de la última respuesta del bot — encadena turnos para mantener memoria conversacional.",
    )


class BotTestResponse(BaseModel):
    """Output del endpoint POST /bot/test."""
    reply: str
    tools_used: list[str] = Field(default_factory=list, description="Tools que el LLM decidió usar — vacío en el stub")
    response_id: Optional[str] = Field(
        default=None,
        description="ID de esta respuesta, para encadenar como previous_response_id del próximo turno.",
    )
    debug: dict = Field(default_factory=dict, description="Info de diagnóstico para desarrollo")

"""
Modelos SQLAlchemy del bot BCR.

- BotExchange: log de cada intercambio (mensaje → respuesta). Para auditoría,
  debug y para reconstruir conversaciones si hace falta.
- BotSession: memoria conversacional por usuario. Guardamos el último
  response_id de OpenAI por número de WhatsApp para encadenar turnos con
  previous_response_id. Con TTL: si pasaron más de SESSION_TTL_SECONDS sin
  mensajes, la conversación arranca de cero.
- PrecioPizarra: cotizaciones diarias del Mercado Físico de Rosario. Se
  pueblan vía scraper (chunk 3.1) y se consultan vía la tool
  get_precios_pizarra del bot. (producto, fecha) es único — los reruns del
  scraper sobreescriben en lugar de duplicar.

Las tablas se crean automáticamente al arrancar la app (Base.metadata.create_all
en app.py), siempre y cuando este módulo se importe ANTES — el import del
side-effect del registro de modelos ya está agregado en app.py.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from database import Base


# Una conversación se considera "viva" si el último mensaje fue hace menos de
# este tiempo. Pasado ese umbral, el bot arranca fresh (no usa
# previous_response_id). Una hora alcanza para conversaciones normales y
# evita que un usuario que vuelve al día siguiente le pregunte algo y el
# bot retome el hilo viejo.
SESSION_TTL_SECONDS = 60 * 60  # 1 hora


class BotExchange(Base):
    """Un mensaje del usuario + la respuesta del bot. Una fila por turno."""
    __tablename__ = "bot_exchanges"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    from_phone = Column(String, nullable=False, index=True)
    message = Column(Text, nullable=False)
    reply = Column(Text, nullable=False)

    # Metadata operativa para debug.
    response_id = Column(String, nullable=True)  # OpenAI response.id
    tools_used = Column(JSON, nullable=False, default=list)
    iterations = Column(Integer, nullable=False, default=0)

    # Estado del intercambio.
    success = Column(Boolean, nullable=False, default=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class BotSession(Base):
    """Memoria conversacional por número de WhatsApp.

    Una fila por usuario (from_phone es PK). Se actualiza en cada turno; si
    expira por inactividad, el próximo mensaje arranca conversación nueva.
    """
    __tablename__ = "bot_sessions"

    from_phone = Column(String, primary_key=True)
    last_response_id = Column(String, nullable=True)
    last_message_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PrecioPizarra(Base):
    """Cotización del Mercado Físico de Rosario para un (producto, fecha).

    El scraper corre diariamente y hace upsert sobre (producto, fecha). Si
    el sitio actualiza un precio retroactivamente, la fila se actualiza —
    no se duplica."""
    __tablename__ = "precios_pizarra"

    id = Column(Integer, primary_key=True, autoincrement=True)
    producto = Column(String, nullable=False, index=True)  # 'soja', 'trigo', 'maiz', 'girasol', ...
    fecha = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    precio_ars_tn = Column(Float, nullable=False)
    scraped_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("producto", "fecha", name="uix_precio_producto_fecha"),
    )

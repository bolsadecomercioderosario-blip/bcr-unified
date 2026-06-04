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


class IngestedComentario(Base):
    """Tracking de qué comentarios diarios ya subimos al vector store.

    Sin esto, cada corrida del scraper subiría todo de nuevo y duplicaría
    los archivos en OpenAI. Con esto, sólo subimos los nuevos.
    """
    __tablename__ = "ingested_comentarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)  # "local" o "chicago"
    comentario_id = Column(Integer, nullable=False)  # ej. 1711
    fecha = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    fecha_legible = Column(String, nullable=True)  # "20 de Mayo de 2026"
    url = Column(String, nullable=False)
    openai_file_id = Column(String, nullable=True)  # útil para debug
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source", "comentario_id", name="uix_comentario_source_id"),
    )


class BotConfig(Base):
    """KV de configuración runtime del bot — sobre todo para IDs de vector
    stores que se auto-crean cuando no están seteados por env var.

    No usamos esto para secretos: sólo para identifiers de OpenAI que
    sobreviven entre deploys (porque borrarlos accidentalmente fuerza a
    re-ingestar todo desde cero, lo cual es lento y caro).
    """
    __tablename__ = "bot_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class IngestedInformativoArticle(Base):
    """Tracking de qué artículos del Informativo Semanal ya subimos al
    vector store. La key estable es el slug (ej. 'carinata-0', 'la-92')."""
    __tablename__ = "ingested_informativo_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    edicion_numero = Column(Integer, nullable=True, index=True)  # ej. 2243
    edicion_anio_roman = Column(String, nullable=True)  # 'XLV'
    fecha = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    fecha_legible = Column(String, nullable=True)
    titulo = Column(Text, nullable=False)
    seccion = Column(String, nullable=True)  # Commodities, Economía, etc.
    url = Column(String, nullable=False)
    openai_file_id = Column(String, nullable=True)
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class EstimacionGea(Base):
    """Una fila por (cultivo, campaña). El scraper hace upsert: si la BCR
    revisa una estimación a la baja/alta, la fila se actualiza.

    Campos de número son nullable porque el sitio a veces deja vacías
    celdas de rinde/producción para campañas en curso (sólo área sembrada)."""
    __tablename__ = "estimaciones_gea"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cultivo = Column(String, nullable=False, index=True)  # 'soja', 'trigo', 'maiz', 'girasol'
    campania = Column(String, nullable=False, index=True)  # '2025/26', '2026/27'
    area_sembrada_mha = Column(Float, nullable=True)
    rinde_qq_ha = Column(Float, nullable=True)
    produccion_mtn = Column(Float, nullable=True)
    scraped_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("cultivo", "campania", name="uix_gea_cultivo_campania"),
    )


class IngestedGeaReport(Base):
    """Tracking de qué informes mensuales de GEA (Estimación Nacional de
    Producción) ya subimos al vector store. Slug del URL es la key estable."""
    __tablename__ = "ingested_gea_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    fecha = Column(String, nullable=False, index=True)
    fecha_legible = Column(String, nullable=True)
    titulo = Column(Text, nullable=False)
    autor = Column(String, nullable=True)
    url = Column(String, nullable=False)
    openai_file_id = Column(String, nullable=True)
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CursoCapacita(Base):
    """Cada fila es un curso/charla del catálogo de BCR Capacita.

    `curso_id_externo` es el ID del CMS (numérico, ej. 842) que aparece en
    la URL del detalle (/capacitacion/cursos-charlas/{ID}). UNIQUE para
    permitir upsert: si la BCR cambia fecha/descripcion/arancel, la fila se
    actualiza en lugar de duplicar.
    """
    __tablename__ = "cursos_capacita"

    id = Column(Integer, primary_key=True, autoincrement=True)
    curso_id_externo = Column(Integer, nullable=False, unique=True, index=True)
    titulo = Column(Text, nullable=False)
    fecha_inicio = Column(String, nullable=True, index=True)  # YYYY-MM-DD
    fecha_inicio_legible = Column(String, nullable=True)  # 05/06/2026
    descripcion = Column(Text, nullable=True)
    modalidad = Column(String, nullable=True)  # presencial / online / mixta
    arancel = Column(Text, nullable=True)
    duracion = Column(Text, nullable=True)
    url = Column(String, nullable=False)
    scraped_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class IngestedNovedadInnova(Base):
    """Tracking de novedades de BCR Innova (/novedades) que ya subimos al
    vector store. node_id del URL Drupal es la key estable."""
    __tablename__ = "ingested_novedades_innova"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(Integer, nullable=False, unique=True, index=True)
    titulo = Column(Text, nullable=False)
    fecha = Column(String, nullable=True, index=True)  # YYYY-MM-DD
    fecha_legible = Column(String, nullable=True)
    descripcion_breve = Column(Text, nullable=True)
    url = Column(String, nullable=False)
    openai_file_id = Column(String, nullable=True)
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class StartupInnova(Base):
    """Cada fila es una startup del Startup Network. UNIQUE por (nombre,
    edicion) — la misma startup puede aparecer en varias ediciones de la red.
    """
    __tablename__ = "startups_innova"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String, nullable=False, index=True)
    sector = Column(String, nullable=True, index=True)  # Agrifoodtech, Biotech, Fintech, etc.
    edicion = Column(String, nullable=True)  # 'BCR SN 6.0' por ejemplo
    descripcion = Column(Text, nullable=True)
    website_url = Column(String, nullable=True)
    scraped_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("nombre", "edicion", name="uix_startup_nombre_edicion"),
    )

"""
Helpers para vector stores de OpenAI con auto-bootstrap.

Para los 4 vector stores del bot (institucional, informativo, comentarios,
gea), aceptamos dos formas de configurar el ID:

1. **Env var** (BOT_VS_<NOMBRE>) — modo legacy, útil cuando el VS se creó
   manualmente y querés que el código lo use sin tocar la DB.
2. **Auto-bootstrap en DB** — si el env var no está seteado, el scraper
   correspondiente crea el vector store la primera vez que corre y persiste
   el ID en la tabla bot_config. En sucesivas corridas usa el ID guardado.

Esto resuelve un problema concreto: sumar una fuente nueva no debería
requerir que el usuario abra OpenAI, cree un vector store, copie un ID,
lo pegue en Render, y reinicie. Con auto-bootstrap deployás el código y
el bot se ocupa.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from openai import OpenAI
from sqlalchemy.orm import Session

from config import (
    BOT_VS_COMENTARIOS,
    BOT_VS_GEA,
    BOT_VS_INFORMATIVO,
    BOT_VS_INSTITUCIONAL,
)

from bot.db_models import BotConfig


SourceKey = Literal["institucional", "informativo", "comentarios", "gea"]


# Mapeo a las env vars existentes — si están seteadas, ganan.
_ENV_VAR_OVERRIDES: dict[SourceKey, str | None] = {
    "institucional": BOT_VS_INSTITUCIONAL,
    "informativo": BOT_VS_INFORMATIVO,
    "comentarios": BOT_VS_COMENTARIOS,
    "gea": BOT_VS_GEA,
}

# Nombres human-friendly para los vector stores que el bot auto-crea en OpenAI.
_AUTO_CREATE_NAMES: dict[SourceKey, str] = {
    "institucional": "BCR Bot — Institucional",
    "informativo": "BCR Bot — Informativo Semanal",
    "comentarios": "BCR Bot — Comentarios Diarios",
    "gea": "BCR Bot — Informes GEA",
}


def _config_key(source: SourceKey) -> str:
    return f"vs_{source}"


def get_vector_store_id(db: Session, source: SourceKey) -> str | None:
    """Devuelve el VS ID configurado para una fuente, o None si no hay.

    Orden: env var > DB. Si ninguna tiene valor, devuelve None y la tool
    correspondiente puede degradar (o el scraper puede llamar
    ensure_vector_store_id para auto-crear).
    """
    env_val = _ENV_VAR_OVERRIDES.get(source)
    if env_val:
        return env_val

    config = db.query(BotConfig).filter(BotConfig.key == _config_key(source)).first()
    if config and config.value:
        return config.value

    return None


def ensure_vector_store_id(db: Session, source: SourceKey, client: OpenAI) -> str:
    """Devuelve el VS ID, creándolo en OpenAI si no existe.

    Idempotente — sucesivas llamadas devuelven el mismo ID. Se llama desde
    los scrapers antes de subir archivos, así si es la primera corrida
    de la fuente, se crea el VS con un nombre legible y se persiste el ID.
    """
    existing = get_vector_store_id(db, source)
    if existing:
        return existing

    name = _AUTO_CREATE_NAMES[source]
    vs = client.vector_stores.create(name=name)
    new_id = vs.id

    config = db.query(BotConfig).filter(BotConfig.key == _config_key(source)).first()
    if config is None:
        db.add(BotConfig(key=_config_key(source), value=new_id, updated_at=datetime.utcnow()))
    else:
        config.value = new_id
        config.updated_at = datetime.utcnow()
    db.commit()

    print(f"[bot.vs] Auto-creado vector store '{name}' = {new_id} (source={source})")
    return new_id


def upload_text_file(
    client: OpenAI,
    vector_store_id: str,
    filename: str,
    content: str,
) -> str:
    """Sube un TXT al vector store y devuelve el file_id.

    Hace 2 pasos: upload del archivo crudo (purpose='assistants') + add al
    vector store. OpenAI procesa la chunkificación y la indexación de manera
    asincrónica — si necesitamos esperar a que termine, podríamos pollear
    el status, pero para nuestro caso (ingest batch antes del próximo
    request de usuario) la indexación es lo suficientemente rápida.
    """
    # OpenAI requiere bytes con un filename — armamos una tupla
    # (filename, bytes) que el SDK acepta como file.
    file_resp = client.files.create(
        file=(filename, content.encode("utf-8")),
        purpose="assistants",
    )
    client.vector_stores.files.create(
        vector_store_id=vector_store_id,
        file_id=file_resp.id,
    )
    return file_resp.id

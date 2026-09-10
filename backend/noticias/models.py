"""
Modelos del módulo Noticias (sitio Más BCR — Fuente de Noticias).

Un solo modelo por ahora: Noticia. El cuerpo se guarda como HTML (lo produce el
editor del admin). El sitio público se renderiza server-side (SEO), así que no hay
SPA pública — sólo el admin es JS.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


# Categorías disponibles (dropdown del admin + menú del sitio). Ampliable.
CATEGORIAS = [
    "Institucional",
    "Mercados y Granos",
    "Innovación",
    "Sostenibilidad",
    "Cultura",
    "Internacional",
]


class Noticia(Base):
    __tablename__ = "noticias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    titulo = Column(Text, nullable=False)
    bajada = Column(Text, nullable=True)
    cuerpo = Column(Text, nullable=True)  # HTML del cuerpo
    imagen_portada = Column(String, nullable=True)  # URL (Cloudinary o /static/uploads)
    categoria = Column(String, nullable=True, index=True)
    estado = Column(String, nullable=False, default="borrador")  # borrador | publicado
    fecha_pub = Column(DateTime, nullable=True)  # se setea al publicar
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class NoticiaIn(BaseModel):
    """Payload para crear/editar desde el admin."""
    titulo: str
    bajada: Optional[str] = None
    cuerpo: Optional[str] = None
    imagen_portada: Optional[str] = None
    categoria: Optional[str] = None
    estado: Optional[str] = "borrador"  # 'borrador' | 'publicado'

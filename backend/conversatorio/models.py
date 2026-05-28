"""
Modelos del módulo Conversatorio a la carta.

Una sola tabla: `conversatorio_sugerencias`. Guarda lo que los socios mandan
desde el formulario público + metadatos (fecha, IP) para moderar si llega
spam.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class Sugerencia(Base):
    __tablename__ = "conversatorio_sugerencias"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    nombre = Column(String(120), default="")
    email = Column(String(200), default="")
    tema = Column(String(500), nullable=False)
    comentarios = Column(Text, default="")
    ip = Column(String(64), default="")

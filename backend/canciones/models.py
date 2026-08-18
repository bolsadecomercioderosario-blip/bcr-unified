"""
Módulo Canciones — versión B de la encuesta: armar la versión reducida eligiendo
SOLO canciones. Misma mecánica que `corte`, tabla propia `canciones_respuestas`.
Las canciones viven en data.py.
"""
from datetime import datetime
from typing import List

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class CancionRespuesta(Base):
    __tablename__ = "canciones_respuestas"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    seleccion = Column(Text, default="[]")   # JSON: [1, 5, 13, ...] (ids de canciones)
    total_seg = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RespuestaIn(BaseModel):
    nombre: str
    seleccion: List[int] = []

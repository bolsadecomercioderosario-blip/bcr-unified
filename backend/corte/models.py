"""
Módulo Corte — encuesta para armar la versión reducida (~30') de "El Más Acá".

Cada murguista carga su nombre y marca los bloques que conservaría; la app
muestra la duración acumulada en vivo. Sin login: upsert por nombre (si la
persona vuelve con el mismo nombre, edita su respuesta). Tabla prefijada
`corte_`. Los bloques del espectáculo viven en data.py.
"""
from datetime import datetime
from typing import List

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class CorteRespuesta(Base):
    __tablename__ = "corte_respuestas"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    seleccion = Column(Text, default="[]")   # JSON: [1, 5, 13, ...] (ids de bloques)
    total_seg = Column(Integer, default=0)   # calculado server-side al guardar
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RespuestaIn(BaseModel):
    nombre: str
    seleccion: List[int] = []

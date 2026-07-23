"""
Módulo Disponibilidad — relevamiento simple de disponibilidad horaria.

Cada persona carga su nombre y marca en qué franjas está disponible (Lunes a
Viernes, bloques de 1 hora de 8 a 20). Sin login. Tabla prefijada `disp_`.
Las franjas se guardan como JSON de strings tipo "mon-8" en una sola columna.
"""
from datetime import datetime
from typing import List

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


class DispResponse(Base):
    __tablename__ = "disp_responses"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    slots = Column(Text, default="[]")   # JSON: ["mon-8", "tue-14", ...]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResponseIn(BaseModel):
    name: str
    slots: List[str] = []


class AdminLogin(BaseModel):
    password: str

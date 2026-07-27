"""
Módulo Murga — sorteo del estreno de "El Más Acá… ¿Hay vida después del
nacimiento?" de la murga "Y Parió La Abuela" (8 de agosto).

App de un solo uso: la gente escanea un QR, completa el formulario (nombre,
celular y "última voluntad") y antes de la función el presentador sortea una
remera entre los inscriptos. Tabla prefijada `murga_`.
"""
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from database import Base


class Participante(Base):
    __tablename__ = "murga_participantes"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    celular = Column(String(50), nullable=False)
    voluntad = Column(Text, nullable=False)
    # Se marca en true cuando la persona ya salió sorteada, para poder
    # excluirla de un re-sorteo. Persistido para que un refresh lo recuerde.
    excluido = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ParticipanteIn(BaseModel):
    nombre: str
    celular: str
    voluntad: str


class ExcluirIn(BaseModel):
    excluido: bool = True

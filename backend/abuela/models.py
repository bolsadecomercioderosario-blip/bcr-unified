"""
Módulo Abuela — panel interno de gestión de la murga "Y Parió La Abuela".
Reemplaza los Excels de caja, toques y asistencia a ensayos. Uso interno,
protegido por contraseña. Tablas prefijadas `ab_`.

Tres secciones:
  - Caja (tesorería): movimientos ingreso/egreso por cuenta + proyección + remeras.
  - Ensayos: asistencia con código P/T/M/A/X y puntaje por murguista.
  - Toques: ficha de condiciones de cada fecha + quién subió al escenario.
"""
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, Float, Integer, String, Text

from database import Base


# Puntaje de cada código de asistencia a ensayos (según hoja "Criterios").
PUNTAJE = {"P": 1.0, "T": 0.5, "M": 0.3, "A": 0.0, "X": -0.5}


class Murguista(Base):
    __tablename__ = "ab_murguistas"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(80), nullable=False)        # apodo canónico (Santi, Chimi, ...)
    nombre_completo = Column(String(200), default="")
    activo = Column(Boolean, default=True)             # False para integrantes históricos
    orden = Column(Integer, default=0)


class CajaMov(Base):
    __tablename__ = "ab_caja_mov"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    fecha = Column(String(10), default="")            # YYYY-MM-DD
    cuenta = Column(String(60), default="")           # ClaroPay / Brubank
    tipo = Column(String(20), default="Egreso")       # Ingreso / Egreso
    monto = Column(Float, default=0.0)
    concepto = Column(String(400), default="")
    proyectado = Column(Boolean, default=False)       # True = movimiento futuro estimado
    created_at = Column(String(32), default=lambda: datetime.utcnow().isoformat())


class Remera(Base):
    __tablename__ = "ab_remera"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(120), nullable=False)
    pago = Column(Boolean, default=False)
    monto = Column(Float, default=20000.0)
    nota = Column(String(200), default="")


class Toque(Base):
    __tablename__ = "ab_toque"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(200), default="")
    fecha = Column(String(40), default="")
    lugar = Column(String(200), default="")
    evento = Column(String(200), default="")
    condicion_eco = Column(String(200), default="")   # cachet / % / gratuito / viáticos...
    duracion = Column(String(80), default="")
    horario = Column(String(200), default="")
    sonido = Column(String(200), default="")
    prueba_sonido = Column(String(200), default="")
    camarin = Column(String(200), default="")
    cachet = Column(String(200), default="")
    factura = Column(String(80), default="")
    entradas = Column(String(200), default="")
    viaticos = Column(String(200), default="")
    comida = Column(String(200), default="")
    bebida = Column(String(200), default="")
    otros = Column(Text, default="")
    contacto = Column(String(200), default="")
    encargado = Column(String(120), default="")
    repertorio = Column(String(200), default="")
    orden = Column(Integer, default=0)
    created_at = Column(String(32), default=lambda: datetime.utcnow().isoformat())


class ToqueAsist(Base):
    __tablename__ = "ab_toque_asist"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    toque_id = Column(Integer, index=True)
    nombre = Column(String(120), default="")
    subio = Column(Boolean, default=False)


class Ensayo(Base):
    __tablename__ = "ab_ensayo"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    periodo = Column(String(60), default="")          # "2026-1er Semestre", ...
    fecha = Column(String(20), default="")            # YYYY-MM-DD (o etiqueta)
    orden = Column(Integer, default=0)


class EnsayoAsist(Base):
    __tablename__ = "ab_ensayo_asist"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ensayo_id = Column(Integer, index=True)
    nombre = Column(String(120), default="")
    codigo = Column(String(4), default="")            # P / T / M / A / X


# ---------------- Pydantic (entrada) ----------------
class MovIn(BaseModel):
    fecha: str = ""
    cuenta: str = ""
    tipo: str = "Egreso"
    monto: float = 0.0
    concepto: str = ""
    proyectado: bool = False


class RemeraIn(BaseModel):
    nombre: str
    pago: bool = False
    monto: float = 20000.0
    nota: str = ""


class ToqueIn(BaseModel):
    nombre: str = ""
    fecha: str = ""
    lugar: str = ""
    evento: str = ""
    condicion_eco: str = ""
    duracion: str = ""
    horario: str = ""
    sonido: str = ""
    prueba_sonido: str = ""
    camarin: str = ""
    cachet: str = ""
    factura: str = ""
    entradas: str = ""
    viaticos: str = ""
    comida: str = ""
    bebida: str = ""
    otros: str = ""
    contacto: str = ""
    encargado: str = ""
    repertorio: str = ""


class EnsayoIn(BaseModel):
    periodo: str = ""
    fecha: str = ""


class MarcaIn(BaseModel):
    ensayo_id: int
    nombre: str
    codigo: str


class ToqueSubioIn(BaseModel):
    toque_id: int
    nombre: str
    subio: bool

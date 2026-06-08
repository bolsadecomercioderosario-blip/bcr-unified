"""
Modelos del módulo Métricas FBCR.

Dos tablas:
  - metricas_programas: catálogo de programas de la Fundación (OSC, Agromakers,
    Empresas, etc.). Define cómo se muestra cada uno en el dashboard.
  - metricas_instancias: cada edición/evento concreto de un programa. Acá viven
    las métricas. Todos los campos numéricos son nullable porque la planilla
    original es artesanal: muchas instancias sólo tienen algunos datos cargados.

El esquema es deliberadamente flexible (un montón de campos opcionales) para que
toda la heterogeneidad del Excel entre sin forzar, y para que el formulario de
alta sirva igual para una edición de OSC o una capacitación a empresas.
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


class Programa(Base):
    __tablename__ = "metricas_programas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    slug = Column(String(60), unique=True, nullable=False, index=True)
    nombre = Column(String(160), nullable=False)
    descripcion = Column(Text, default="")
    icono = Column(String(16), default="")          # emoji para las tarjetas
    color = Column(String(16), default="#0ea5e9")    # acento hex del programa
    orden = Column(Integer, default=0)               # orden de aparición
    activo = Column(Integer, default=1)              # 0 = oculto del dashboard

    instancias = relationship(
        "Instancia",
        back_populates="programa",
        cascade="all, delete-orphan",
    )


class Instancia(Base):
    __tablename__ = "metricas_instancias"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    programa_id = Column(
        Integer,
        ForeignKey("metricas_programas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    titulo = Column(String(300), nullable=False)     # "1ª Edición", "Final 9na", etc.
    anio = Column(Integer, nullable=True, index=True)  # para agrupar/graficar
    fecha = Column(Date, nullable=True)              # fecha exacta si se conoce
    fecha_texto = Column(String(120), default="")    # texto crudo si la fecha es difusa
    modalidad = Column(String(120), default="")
    localidades = Column(Text, default="")

    # Métricas numéricas (todas opcionales)
    personas = Column(Integer, nullable=True)        # personas alcanzadas / participantes
    proyectos = Column(Integer, nullable=True)
    osc = Column(Integer, nullable=True)             # organizaciones de la sociedad civil
    escuelas = Column(Integer, nullable=True)
    mentores = Column(Integer, nullable=True)
    monto = Column(Float, nullable=True)             # donaciones / aportes en $

    # Texto libre
    ganadores = Column(Text, default="")
    reconocimiento = Column(Text, default="")        # premios, declaraciones, links
    notas = Column(Text, default="")

    orden = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    programa = relationship("Programa", back_populates="instancias")

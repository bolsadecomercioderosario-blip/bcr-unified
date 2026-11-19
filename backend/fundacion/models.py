"""
Modelo del módulo Agenda de la Fundación BCR.

Una sola tabla, deliberadamente simple (espeja la planilla de origen):
`fundacion_actividades`. Cada fila es una actividad con fecha, hora (texto libre,
puede ser un rango "08:00 a 12:00 hs"), descripción del evento, equipo que
participa y una métrica opcional. No tiene la complejidad de la Agenda de
Comunicación/Secretaría (roles, cobertura, Mesa): es una agenda plana que las
autoridades de la Fundación consultan y que Anaclara carga (web o WhatsApp).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, String, Text

from database import Base


class FundacionActividad(Base):
    __tablename__ = "fundacion_actividades"

    id = Column(String, primary_key=True, index=True)
    fecha = Column(String, default="", index=True)   # ISO 'YYYY-MM-DD'
    hora = Column(String, default="")                # texto libre ("15 hs", rango…)
    evento = Column(Text, default="")
    equipo = Column(String, default="")
    metricas = Column(String, default="")

    # Procedencia del registro: "import" (seed de la planilla) | "web" | "whatsapp".
    origen = Column(String, default="web")
    # Auditoría: email/rol de quién lo cargó ("import", "whatsapp:<phone>", …).
    created_by = Column(String, default="")
    created_at = Column(String, default="")          # ISO UTC
    updated_at = Column(String, default="")          # ISO UTC

    # Soft-delete (nunca se borra físicamente; queda recuperable).
    archived = Column(Boolean, default=False)
    archived_at = Column(String, default="")


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# --- Schemas ----------------------------------------------------------------
class ActividadIn(BaseModel):
    fecha: str = ""          # 'YYYY-MM-DD'
    hora: Optional[str] = ""
    evento: str = ""
    equipo: Optional[str] = ""
    metricas: Optional[str] = ""


class ActividadOut(BaseModel):
    id: str
    fecha: str = ""
    hora: str = ""
    evento: str = ""
    equipo: str = ""
    metricas: str = ""
    origen: str = ""

    class Config:
        from_attributes = True

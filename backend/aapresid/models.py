"""
Modelos del módulo Aapresid 2026 — organización de la presencia de la BCR en el
Congreso Aapresid (Salón Metropolitano, Rosario, 4-6 ago 2026).

Todas las tablas van prefijadas `aap_` para no colisionar con otros módulos.
Fechas de negocio como String 'YYYY-MM-DD', horas como 'HH:MM'. Los timestamps
de auditoría (created_at/updated_at) son DateTime UTC.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


# ---------------------------------------------------------------------------
# SQLAlchemy — tablas
# ---------------------------------------------------------------------------
class AapEvent(Base):
    __tablename__ = "aap_events"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    location = Column(String(300), default="")
    start_date = Column(String(10), nullable=False)   # YYYY-MM-DD
    end_date = Column(String(10), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapShift(Base):
    __tablename__ = "aap_shifts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("aap_events.id"), nullable=False)
    date = Column(String(10), nullable=False)         # YYYY-MM-DD
    name = Column(String(60), nullable=False)         # "Mañana" | "Mediodía" | "Tarde"
    start_time = Column(String(5), nullable=False)    # HH:MM
    end_time = Column(String(5), nullable=False)
    display_order = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    # Responsable del turno: texto libre (alguien escribe quién es).
    responsible_name = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapArea(Base):
    __tablename__ = "aap_areas"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(160), nullable=False)
    description = Column(String(500), default="")
    responsible = Column(String(160), default="")     # responsable de referencia (texto libre)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapPerson(Base):
    __tablename__ = "aap_people"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(200), nullable=False)
    area_id = Column(Integer, ForeignKey("aap_areas.id"), nullable=True)
    role = Column(String(160), default="")            # cargo/función
    email = Column(String(200), default="")
    phone = Column(String(60), default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapAttendance(Base):
    __tablename__ = "aap_attendance"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("aap_events.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("aap_shifts.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("aap_people.id"), nullable=False)
    start_time = Column(String(5), default="")        # hora de ingreso (opcional)
    end_time = Column(String(5), default="")          # hora de salida (opcional)
    is_shift_responsible = Column(Boolean, default=False)
    event_role = Column(String(200), default="")      # función durante el evento
    notes = Column(String(1000), default="")
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapMeeting(Base):
    __tablename__ = "aap_meetings"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("aap_events.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("aap_shifts.id"), nullable=True)  # calculado por horario
    title = Column(String(300), nullable=False)
    organization = Column(String(300), default="")    # legacy, sin uso
    external_participants = Column(String(1000), default="")  # legacy, sin uso
    date = Column(String(10), nullable=False)
    start_time = Column(String(5), nullable=False, default="")  # ya no se usa hora
    end_time = Column(String(5), default="")
    location = Column(String(300), default="")        # "Stand BCR" u otro espacio
    area_name = Column(String(200), default="")       # área de la BCR (texto libre)
    responsible_name = Column(String(200), default="")  # quién carga (texto libre)
    responsible_person_id = Column(Integer, ForeignKey("aap_people.id"), nullable=True)  # legacy, sin uso
    description = Column(Text, default="")
    notes = Column(Text, default="")
    status = Column(String(20), default="Tentativa")  # Tentativa|Confirmada|Realizada|Cancelada
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapMeetingParticipant(Base):
    __tablename__ = "aap_meeting_participants"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("aap_meetings.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("aap_people.id"), nullable=False)


class AapUser(Base):
    __tablename__ = "aap_users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(200), default="")
    email = Column(String(200), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), default="")
    role = Column(String(20), default="editor")       # "admin" | "editor"
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AapAudit(Base):
    __tablename__ = "aap_audit_log"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True)
    user_email = Column(String(200), default="")
    entity_type = Column(String(60), default="")
    entity_id = Column(Integer, nullable=True)
    action = Column(String(20), default="")           # create|update|delete
    previous_data = Column(Text, default="")          # JSON
    new_data = Column(Text, default="")               # JSON
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Pydantic — schemas (Fase 1)
# ---------------------------------------------------------------------------
class AreaIn(BaseModel):
    name: str
    description: Optional[str] = ""
    responsible: Optional[str] = ""
    active: Optional[bool] = True


class AreaOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = ""
    responsible: Optional[str] = ""
    active: bool

    class Config:
        from_attributes = True


class PersonIn(BaseModel):
    full_name: str
    area_id: Optional[int] = None
    role: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    active: Optional[bool] = True


class PersonOut(BaseModel):
    id: int
    full_name: str
    area_id: Optional[int] = None
    role: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    active: bool

    class Config:
        from_attributes = True


class AttendanceIn(BaseModel):
    shift_id: int
    person_id: int
    start_time: Optional[str] = ""
    end_time: Optional[str] = ""
    is_shift_responsible: Optional[bool] = False
    event_role: Optional[str] = ""
    notes: Optional[str] = ""


class AttendanceUpdate(BaseModel):
    shift_id: Optional[int] = None
    person_id: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_shift_responsible: Optional[bool] = None
    event_role: Optional[str] = None
    notes: Optional[str] = None


class AttendanceOut(BaseModel):
    id: int
    event_id: int
    shift_id: int
    person_id: int
    start_time: Optional[str] = ""
    end_time: Optional[str] = ""
    is_shift_responsible: bool
    event_role: Optional[str] = ""
    notes: Optional[str] = ""

    class Config:
        from_attributes = True


class ShiftOut(BaseModel):
    id: int
    event_id: int
    date: str
    name: str
    start_time: str
    end_time: str
    display_order: int
    active: bool
    responsible_name: Optional[str] = ""

    class Config:
        from_attributes = True


class ShiftResponsibleIn(BaseModel):
    responsible_name: Optional[str] = ""


class ShiftIn(BaseModel):
    date: str
    name: str
    start_time: str
    end_time: str
    display_order: Optional[int] = 0
    active: Optional[bool] = True


class EventOut(BaseModel):
    id: int
    name: str
    location: Optional[str] = ""
    start_date: str
    end_date: str
    active: bool

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: int
    full_name: Optional[str] = ""
    email: str
    role: str
    active: bool

    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    email: str
    password: str


MEETING_STATUSES = ["Tentativa", "Confirmada"]


class MeetingIn(BaseModel):
    shift_id: int
    title: str                                # descripción / tema
    responsible_name: Optional[str] = ""      # quién carga (texto libre)
    area_name: Optional[str] = ""             # área de la BCR (texto libre)
    location: Optional[str] = ""              # "Stand BCR" u otro espacio
    status: Optional[str] = "Tentativa"


class MeetingOut(BaseModel):
    id: int
    event_id: int
    shift_id: Optional[int] = None
    title: str
    responsible_name: Optional[str] = ""
    area_name: Optional[str] = ""
    location: Optional[str] = ""
    date: str
    status: str

    class Config:
        from_attributes = True

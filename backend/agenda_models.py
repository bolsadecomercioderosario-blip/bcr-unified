from sqlalchemy import Column, String, Boolean, Integer, JSON
from pydantic import BaseModel
from typing import List, Optional
from database import Base

# SQLAlchemy Model (DB Table)
class Activity(Base):
    __tablename__ = "activities"

    id = Column(String, primary_key=True, index=True)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    # Multi-día: si end_date está seteado y es posterior a date, la actividad se
    # extiende de date a end_date y se muestra en cada día del rango. Vacío = un
    # solo día (comportamiento por defecto de todo lo ya cargado).
    end_date = Column(String, default="")
    # Rango horario opcional: si end_time está, se muestra "HH:MM a HH:MM".
    end_time = Column(String, default="")
    title = Column(String, nullable=False)
    description = Column(String, default="")
    location = Column(String, default="")
    observations = Column(String, default="")
    responsible = Column(String, default="")
    external_name = Column(String, default="")
    channels = Column(JSON, default=list) # Stores the list of channels
    done = Column(Boolean, default=False)
    drive_bcr = Column(String, default="")
    drive_santiago = Column(String, default="")
    copy_instagram = Column(String, default="")
    copy_linkedin = Column(String, default="")
    participants = Column(String, default="")
    story_type = Column(String, default="Video")
    conectados_title = Column(String, default="")
    conectados_text = Column(String, default="")
    is_custom = Column(Boolean, default=False)
    order_index = Column(Integer, default=0)
    image_url = Column(String, default="")
    # "fixed" | "variable" | None — None significa que es una actividad normal,
    # no un bloque de newsletter. Reemplaza el viejo flag observations='FIXED_BLOCK'
    # que era frágil (cualquier edit del form lo pisaba).
    block_type = Column(String, nullable=True, default=None)
    # Origen / dueño de la actividad. Define en qué superficie aparece:
    #   "secretaria"   → la carga Secretaría; es parte de la Agenda de
    #                    Compromisos (se ve en la landing pública y la edita
    #                    Secretaría). Comunicación la ve, pero los Datos
    #                    Generales son solo-lectura para ella.
    #   "comunicacion" → la crea Comunicación; vive sólo en la app de
    #                    Comunicación, nunca en la landing ni para Secretaría.
    # Reemplaza al viejo canal "Agenda Compromisos".
    origen = Column(String, default="comunicacion")
    # Notas internas de Comunicación sobre la actividad (ej: "va a haber mucha
    # gente, llegar temprano"). Sólo las ve Comunicación — separadas de
    # `observations`, que es un campo de Datos Generales (de Secretaría).
    comunicacion_notes = Column(String, default="")
    # --- Campos exclusivos de Secretaría (sección "Estado" del form) ---
    # Estado de avance: "Pendiente" | "En Proceso" | "Avanzado" | "Finalizado".
    # Alimenta el semáforo (barra de color) del listado de Secretaría.
    estado = Column(String, default="Pendiente")
    # Responsable del evento por el lado de Secretaría (distinto del operativo
    # `responsible`, que es quién lo cubre en Comunicación). Si es "Otro", el
    # nombre va en sec_responsible_other.
    sec_responsible = Column(String, default="")
    sec_responsible_other = Column(String, default="")
    # Archivo adjunto (DOC/DOCX/PDF/JPG/PNG). Lo sube Secretaría; Comunicación lo
    # ve/descarga (solo lectura). No aparece en la landing pública.
    attachment_url = Column(String, default="")
    attachment_name = Column(String, default="")

# Pydantic Models (API Validation)
class ActivityBase(BaseModel):
    id: str
    date: str
    time: str
    end_date: Optional[str] = ""
    end_time: Optional[str] = ""
    title: str
    description: Optional[str] = ""
    location: Optional[str] = ""
    observations: Optional[str] = ""
    responsible: Optional[str] = ""
    external_name: Optional[str] = ""
    channels: List[str] = []
    done: Optional[bool] = False
    drive_bcr: Optional[str] = ""
    drive_santiago: Optional[str] = ""
    copy_instagram: Optional[str] = ""
    copy_linkedin: Optional[str] = ""
    participants: Optional[str] = ""
    story_type: Optional[str] = "Video"
    conectados_title: Optional[str] = ""
    conectados_text: Optional[str] = ""
    is_custom: Optional[bool] = False
    order_index: Optional[int] = 0
    image_url: Optional[str] = ""
    block_type: Optional[str] = None  # "fixed" | "variable" | None
    origen: Optional[str] = "comunicacion"  # "secretaria" | "comunicacion"
    comunicacion_notes: Optional[str] = ""
    estado: Optional[str] = "Pendiente"
    sec_responsible: Optional[str] = ""
    sec_responsible_other: Optional[str] = ""
    attachment_url: Optional[str] = ""
    attachment_name: Optional[str] = ""

class ActivityCreate(ActivityBase):
    pass

class ActivityUpdate(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    end_date: Optional[str] = None
    end_time: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    observations: Optional[str] = None
    responsible: Optional[str] = None
    external_name: Optional[str] = None
    channels: Optional[List[str]] = None
    done: Optional[bool] = None
    drive_bcr: Optional[str] = None
    drive_santiago: Optional[str] = None
    copy_instagram: Optional[str] = None
    copy_linkedin: Optional[str] = None
    participants: Optional[str] = None
    story_type: Optional[str] = None
    conectados_title: Optional[str] = None
    conectados_text: Optional[str] = None
    is_custom: Optional[bool] = None
    order_index: Optional[int] = None
    image_url: Optional[str] = None
    block_type: Optional[str] = None
    origen: Optional[str] = None
    comunicacion_notes: Optional[str] = None
    estado: Optional[str] = None
    sec_responsible: Optional[str] = None
    sec_responsible_other: Optional[str] = None
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None

class ActivityOut(ActivityBase):
    class Config:
        from_attributes = True


# Salida acotada para la landing pública de la Agenda de Compromisos.
# Sólo expone los Datos Generales — NO los campos operativos (responsable,
# canales, copies, links, realizado) ni las notas internas de Comunicación.
# Es deliberadamente angosto: la landing es pública (token en la URL) y no debe
# filtrar nada de uso interno.
class CompromisoPublicOut(BaseModel):
    id: str
    date: str
    time: str
    end_date: Optional[str] = ""
    end_time: Optional[str] = ""
    title: str
    description: Optional[str] = ""
    location: Optional[str] = ""
    observations: Optional[str] = ""
    participants: Optional[str] = ""
    # Adjunto: se expone en la pública como "Ver Información Adicional". OJO: esto
    # hace el archivo descargable por cualquiera con el link público (token).
    attachment_url: Optional[str] = ""
    attachment_name: Optional[str] = ""

    class Config:
        from_attributes = True

class GenerateCopyRequest(BaseModel):
    mode: str  # 'ig' | 'li' | 'newsletter_block'
    title: str
    description: Optional[str] = ""
    observations: Optional[str] = ""
    participants_enriched: Optional[str] = ""
    # newsletter_block: texto base del que se parte (LinkedIn, Instagram, o
    # info cruda de la actividad — el front decide la prioridad).
    base_text: Optional[str] = ""
    base_source: Optional[str] = ""  # 'linkedin' | 'instagram' | 'basic'


# Efemérides y Aniversarios (recurrentes anuales — sin año)
class Efemeride(Base):
    __tablename__ = "efemerides"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mes = Column(Integer, nullable=False)
    dia = Column(Integer, nullable=False)
    tipo = Column(String, default="Efeméride")  # "Efeméride" | "Aniversario"
    motivo = Column(String, nullable=False)


class EfemerideBase(BaseModel):
    mes: int
    dia: int
    tipo: str = "Efeméride"
    motivo: str


class EfemerideCreate(EfemerideBase):
    pass


class EfemerideUpdate(BaseModel):
    mes: Optional[int] = None
    dia: Optional[int] = None
    tipo: Optional[str] = None
    motivo: Optional[str] = None


class EfemerideOut(EfemerideBase):
    id: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Newsletter Conectados — settings de "edición actual" (singleton).
# Define el rango temporal que enmarca la edición que se está armando.
# Las actividades del canal Conectados que caen en [start_at, end_at] se
# muestran en la pestaña; las que quedan afuera, no. Bloques fijos y
# variables (is_custom) no se filtran por rango.
# ---------------------------------------------------------------------------
class NewsletterSettings(Base):
    __tablename__ = "newsletter_settings"

    # id fijo en 1 — solo hay una fila. Más simple que un kv genérico.
    id = Column(Integer, primary_key=True, default=1)
    # ISO 8601: "YYYY-MM-DDTHH:MM" (compatible con datetime-local del browser).
    edition_start_at = Column(String, nullable=False)
    edition_end_at = Column(String, nullable=False)


class NewsletterSettingsOut(BaseModel):
    edition_start_at: str
    edition_end_at: str

    class Config:
        from_attributes = True


class NewsletterSettingsUpdate(BaseModel):
    edition_start_at: str
    edition_end_at: str

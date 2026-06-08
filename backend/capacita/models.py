"""
Modelos del módulo "BCR Capacita — captación de leads".

Una sola tabla: `capacita_leads`. Guarda los datos de contacto que deja la
gente desde el formulario público de campaña (llegan por publicidad en redes)
+ metadatos (fecha, origen, IP) para depurar y medir.

Las áreas de interés se guardan como JSON serializado en una columna Text:
algunas opciones tienen comas en el nombre ("Innovación, Tecnología y Datos"),
así que no se puede usar un simple join por coma.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from database import Base


class CapacitaLead(Base):
    __tablename__ = "capacita_leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Datos de contacto — al menos uno de los dos viene cargado (se valida en
    # el router y en el front).
    email = Column(String(200), default="")
    whatsapp = Column(String(40), default="")

    # Lista de áreas de interés, serializada como JSON (["Mercado...", ...]).
    intereses = Column(Text, default="[]")

    # Consentimiento de contacto. Siempre debería ser True (el form no envía si
    # está desmarcado), pero lo persistimos como evidencia del opt-in.
    autorizacion = Column(Boolean, default=True, nullable=False)

    # Trazabilidad de la campaña.
    origen = Column(String(64), default="")  # ej: "redes"
    ip = Column(String(64), default="")

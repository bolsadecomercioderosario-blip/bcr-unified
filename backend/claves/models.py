"""
Modelos del módulo "Claves — recortes" (Fase C).

Dos tablas:
 - `claves_programas`: un programa semanal (video de YouTube) con sus candidatos
   de recorte ya propuestos. Los candidatos se guardan como JSON (son propuestas
   de solo lectura: timecode, texto, tópico, miniatura).
 - `claves_renders`: pedidos de generación de un reel (un candidato elegido) y su
   resultado. La UI crea el pedido (estado 'pendiente'); el worker LOCAL (la PC
   de Comunicación) lo toma, renderiza, sube el MP4 a Cloudinary y marca 'listo'.

El procesamiento pesado (descarga, Whisper, ffmpeg) NO corre en Render: vive en
la PC local. Render solo guarda el estado y sirve la UI al equipo.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from database import Base


class ClavesPrograma(Base):
    __tablename__ = "claves_programas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    video_id = Column(String(32), unique=True, index=True, nullable=False)  # id de YouTube
    title = Column(String(300), default="")
    fecha = Column(String(20), default="")  # fecha del programa (YYYY-MM-DD)

    # Lista de candidatos (JSON): [{cid, topic, start, end, dur, text, thumb_url}]
    candidatos = Column(Text, default="[]")


class ClavesRender(Base):
    __tablename__ = "claves_renders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    video_id = Column(String(32), index=True, nullable=False)
    cid = Column(String(16), nullable=False)       # candidato (c01..)
    zoom = Column(Boolean, default=False)           # zoom-crop de la tarjeta

    estado = Column(String(16), default="pendiente")  # pendiente|procesando|listo|error
    video_url = Column(String(500), default="")       # URL de Cloudinary cuando está listo
    error = Column(Text, default="")
    requested_by = Column(String(200), default="")    # email del que pidió

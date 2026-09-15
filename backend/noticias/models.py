"""
Modelos del módulo Noticias (sitio Más BCR — Fuente de Noticias).

Un solo modelo por ahora: Noticia. El cuerpo se guarda como HTML (lo produce el
editor del admin). El sitio público se renderiza server-side (SEO), así que no hay
SPA pública — sólo el admin es JS.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text

from database import Base


# Categorías de noticias (dropdown del admin + menú del sitio). Tomadas del sitio
# actual masbcr. Ampliable.
CATEGORIAS = [
    "Institucionales",
    "Agroindustria",
    "Mercados",
    "Ganadería",
    "Innovación",
    "Sostenibilidad",
    "Cultura",
    "Empresas",
    "Entrevistas",
]

# Posición/anclaje de una nota en la Home (réplica del selector de WordPress).
# El orden es el que se muestra en el desplegable del admin.
POSICIONES = [
    ("normal", "Sin anclaje"),
    ("principal", "Anclar en Principal"),
    ("sec1", "Anclar en Secundaria 1"),
    ("sec2", "Anclar en Secundaria 2"),
    ("sec3", "Anclar en Secundaria 3"),
    ("no_principal", "No en principales"),
    ("no_home", "No en Home"),
]
_POSICIONES_SET = {k for k, _ in POSICIONES}

# Kit Multimedia: 6 galerías fijas (réplica de masbcr). slug estable + nombre +
# descripción que se muestran en el índice del kit.
KIT_CATEGORIAS = [
    {"slug": "institucional", "nombre": "Institucional",
     "desc": "Imágenes del edificio de la Bolsa de Comercio de Rosario, autoridades, funcionarios y otros."},
    {"slug": "rosario", "nombre": "Rosario",
     "desc": "Imágenes y videos de la ciudad de Rosario y alrededores."},
    {"slug": "cultivos", "nombre": "Cultivos",
     "desc": "Imágenes de cultivos de maíz, soja, trigo y girasol."},
    {"slug": "ganaderia", "nombre": "Ganadería",
     "desc": "Imágenes y videos referentes a la actividad ganadera."},
    {"slug": "logistica", "nombre": "Logística",
     "desc": "Imágenes y videos de transporte de granos: camiones, trenes, barcos, etc."},
    {"slug": "otras", "nombre": "Otras",
     "desc": "Imágenes de gran variedad de actividades."},
]
_KIT_SLUGS = {c["slug"] for c in KIT_CATEGORIAS}
_KIT_NOMBRE = {c["slug"]: c["nombre"] for c in KIT_CATEGORIAS}

# Subcategorías (subtítulos) dentro de ciertas galerías. El orden define el
# orden en que se muestran en la galería pública. Las galerías que no figuran
# acá se muestran planas (sin subtítulos).
KIT_SUBCATS = {
    "institucional": ["Autoridades y funcionarios", "Edificios e instalaciones"],
    "cultivos": ["Soja", "Trigo", "Maíz", "Otros cultivos"],
}


class Noticia(Base):
    __tablename__ = "noticias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    titulo = Column(Text, nullable=False)
    bajada = Column(Text, nullable=True)
    cuerpo = Column(Text, nullable=True)  # HTML del cuerpo
    imagen_portada = Column(String, nullable=True)  # URL (Cloudinary o /static/uploads)
    categoria = Column(String, nullable=True, index=True)
    estado = Column(String, nullable=False, default="borrador")  # borrador | publicado
    posicion = Column(String, nullable=False, default="normal", index=True)  # ver POSICIONES
    fecha_pub = Column(DateTime, nullable=True)  # fecha/hora de publicación (UTC); a futuro = programada
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class NoticiaIn(BaseModel):
    """Payload para crear/editar desde el admin."""
    titulo: str
    bajada: Optional[str] = None
    cuerpo: Optional[str] = None
    imagen_portada: Optional[str] = None
    categoria: Optional[str] = None
    estado: Optional[str] = "borrador"  # 'borrador' | 'publicado'
    posicion: Optional[str] = "normal"  # ver POSICIONES
    fecha_pub: Optional[str] = None     # ISO local (ART) del datetime-local; vacío = ahora


class MediaAsset(Base):
    """Una foto/recurso del Kit Multimedia, dentro de una de las 6 galerías."""
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kit_cat = Column(String, nullable=False, index=True)  # slug de KIT_CATEGORIAS
    subcat = Column(String, nullable=True, index=True)    # subtítulo (ver KIT_SUBCATS)
    url = Column(String, nullable=False)                  # URL Cloudinary o /static/uploads
    titulo = Column(String, nullable=True)
    orden = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MediaAssetIn(BaseModel):
    kit_cat: str
    url: str
    titulo: Optional[str] = None
    subcat: Optional[str] = None


class MediaAssetUpdate(BaseModel):
    subcat: Optional[str] = None


class Video(Base):
    """Video de YouTube para la sección Videos de la home."""
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    youtube_id = Column(String, nullable=False)   # los 11 caracteres del ID
    titulo = Column(String, nullable=True)
    orden = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class VideoIn(BaseModel):
    url: str                      # URL de YouTube (o el ID pelado)
    titulo: Optional[str] = None

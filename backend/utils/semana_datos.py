"""
Generación de la portada de YouTube y armado de título/descripción para el
ciclo "La Semana en Datos".

La portada se construye superponiendo los títulos de 1 o 2 informes sobre la
imagen base ya diseñada (que tiene "La semana en datos" arriba a la izquierda
y el logo BCR abajo). La tipografía es IBM Plex Sans Bold blanca; el tamaño
se auto-ajusta para que el texto entre en el área disponible.
"""
import os
from io import BytesIO
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BACKEND_DIR, "assets", "semana-datos")

FONT_PATH = os.path.join(ASSETS_DIR, "IBMPlexSans-Bold.ttf")
PORTADA_YT_BASE = os.path.join(ASSETS_DIR, "portada-yt-base.png")
PORTADA_REEL_BASE = os.path.join(ASSETS_DIR, "portada-reel-base.png")

# Layout 1920x1080: "La semana en datos" ocupa hasta y≈130, el logo BCR empieza
# en y≈980. Dejamos el bloque de títulos entre esos hitos con un margen lateral
# igual al de "La semana en datos".
TITLE_AREA_LEFT = 60
TITLE_AREA_TOP = 180
TITLE_AREA_RIGHT = 1700
TITLE_AREA_BOTTOM = 940

TITLE_COLOR = (255, 255, 255)
TITLE_MAX_FONT = 90
TITLE_MAX_FONT_TWO = 78  # Cuando hay 2 informes, arrancamos un poco más chico
TITLE_MIN_FONT = 44
LINE_SPACING = 1.12
BLOCK_GAP = 50  # Espacio vertical entre informe 1 y 2 cuando son dos

# Portada Reel 9:16 (900x1600). Un solo título centrado vertical, alineado
# a la izquierda. La base ya tiene "La semana en datos" arriba + logo BCR abajo.
REEL_TITLE_AREA_LEFT = 60
REEL_TITLE_AREA_TOP = 400
REEL_TITLE_AREA_RIGHT = 840
REEL_TITLE_AREA_BOTTOM = 1180
REEL_TITLE_MAX_FONT = 110
REEL_TITLE_MIN_FONT = 55


# Texto institucional fijo que va al pie de cada descripción de YouTube
INSTITUCIONAL = (
    "La Semana en Datos: en cada episodio, economistas de la Bolsa de Comercio "
    "de Rosario explican, de forma clara y directa, los indicadores más "
    "relevantes de los informes publicados por la institución, para entender "
    "qué está pasando en la economía y en los mercados vinculados al agro."
)

INFORMES_URL = "https://www.bcr.com.ar/es/mercados/investigacion-y-desarrollo/informativo-semanal"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Word-wrap a una lista de líneas que entren en `max_width`."""
    words = text.split()
    lines: List[str] = []
    current: List[str] = []
    for w in words:
        test = " ".join(current + [w])
        bbox = font.getbbox(test)
        if (bbox[2] - bbox[0]) <= max_width or not current:
            current.append(w)
        else:
            lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


def _line_height(font: ImageFont.FreeTypeFont) -> float:
    bbox = font.getbbox("ÁyjQ")
    return (bbox[3] - bbox[1]) * LINE_SPACING


def _fit_text(text: str, max_width: int, max_height: int,
              start_size: int, min_size: int):
    """Encuentra el font más grande con el que `text` (con word-wrap) entra en el área."""
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(FONT_PATH, size)
        lines = _wrap_text(text, font, max_width)
        total = _line_height(font) * len(lines)
        if total <= max_height:
            return lines, font
    # Si ni el mínimo entra, lo dibujamos igual con el mínimo (mejor que romper)
    font = ImageFont.truetype(FONT_PATH, min_size)
    return _wrap_text(text, font, max_width), font


def _draw_lines(draw: ImageDraw.ImageDraw, lines: List[str],
                font: ImageFont.FreeTypeFont, x: int, y: float):
    lh = _line_height(font)
    for line in lines:
        draw.text((x, y), line, fill=TITLE_COLOR, font=font)
        y += lh


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def generate_portada_yt(titulos: List[str]) -> bytes:
    """Genera la portada de YouTube para 1 o 2 títulos. Retorna bytes PNG."""
    if not titulos or len(titulos) > 2:
        raise ValueError("Se esperan 1 o 2 títulos")

    base = Image.open(PORTADA_YT_BASE).convert("RGB")
    draw = ImageDraw.Draw(base)

    block_width = TITLE_AREA_RIGHT - TITLE_AREA_LEFT
    block_height = TITLE_AREA_BOTTOM - TITLE_AREA_TOP

    if len(titulos) == 1:
        lines, font = _fit_text(
            titulos[0], block_width, block_height,
            start_size=TITLE_MAX_FONT, min_size=TITLE_MIN_FONT,
        )
        total = _line_height(font) * len(lines)
        y = TITLE_AREA_TOP + (block_height - total) / 2
        _draw_lines(draw, lines, font, TITLE_AREA_LEFT, y)
    else:
        # 2 informes: cada uno tiene como techo una mitad del área, pero los
        # pegamos al centro (1er título termina justo arriba del gap, 2do
        # empieza justo abajo). Así ambos quedan visualmente centrados en
        # vez de uno pegado al header y otro pegado al logo.
        half_h = (block_height - BLOCK_GAP) / 2
        lines1, font1 = _fit_text(
            titulos[0], block_width, half_h,
            start_size=TITLE_MAX_FONT_TWO, min_size=TITLE_MIN_FONT,
        )
        lines2, font2 = _fit_text(
            titulos[1], block_width, half_h,
            start_size=TITLE_MAX_FONT_TWO, min_size=TITLE_MIN_FONT,
        )

        h1 = _line_height(font1) * len(lines1)
        h2 = _line_height(font2) * len(lines2)

        center_y = TITLE_AREA_TOP + block_height / 2
        y1 = center_y - BLOCK_GAP / 2 - h1
        y2 = center_y + BLOCK_GAP / 2

        _draw_lines(draw, lines1, font1, TITLE_AREA_LEFT, y1)
        _draw_lines(draw, lines2, font2, TITLE_AREA_LEFT, y2)

    buf = BytesIO()
    base.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_portada_reel(titulo: str) -> bytes:
    """Genera una portada vertical 9:16 (900x1600) para un Reel/Story.
    El título va centrado verticalmente, alineado a la izquierda, en blanco.
    Se genera UNA portada por informe (1 si el ciclo tiene 1 informe, 2 si hay 2)."""
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("Se espera un título no vacío")

    base = Image.open(PORTADA_REEL_BASE).convert("RGB")
    draw = ImageDraw.Draw(base)

    block_width = REEL_TITLE_AREA_RIGHT - REEL_TITLE_AREA_LEFT
    block_height = REEL_TITLE_AREA_BOTTOM - REEL_TITLE_AREA_TOP

    lines, font = _fit_text(
        titulo, block_width, block_height,
        start_size=REEL_TITLE_MAX_FONT, min_size=REEL_TITLE_MIN_FONT,
    )
    total = _line_height(font) * len(lines)
    y = REEL_TITLE_AREA_TOP + (block_height - total) / 2
    _draw_lines(draw, lines, font, REEL_TITLE_AREA_LEFT, y)

    buf = BytesIO()
    base.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build_title(titulos: List[str]) -> str:
    """Concatena los títulos de los informes con ' | '."""
    return " | ".join(t.strip() for t in titulos if t and t.strip())


def build_description(copetes: List[str], institucional: Optional[str] = None) -> str:
    """Arma la descripción para YouTube siguiendo el template fijo del ciclo."""
    institucional = institucional or INSTITUCIONAL
    body = "\n\n".join(c.strip() for c in copetes if c and c.strip())
    return (
        f"{body}\n\n"
        f"—----\n\n"
        f"{institucional}\n\n"
        f"📊 Un espacio para entender qué dicen los números y por qué importan.\n\n"
        f"📢 Seguinos en nuestras redes sociales: @bolsadecomercioderosario\n\n"
        f"Informes completos:\n{INFORMES_URL}"
    )

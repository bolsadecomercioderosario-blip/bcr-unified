"""
Edición automática de recortes verticales (Reels/Shorts) para "La Semana en Datos".

Toma un recorte 16:9 + un fondo 9:16 + audio del recorte:
  1. Hace resize del recorte a un ancho relativo al fondo.
  2. Lo superpone centrado horizontalmente, a una altura predefinida.
  3. Loopea el fondo si el recorte es más largo.
  4. Transcribe el audio con Whisper API (en español).
  5. Burn-in de subtítulos en MAYÚSCULAS, IBM Plex Sans Bold, blanco,
     debajo del recorte.
  6. Escribe el video resultante a disco.
"""
import math
import os
import tempfile
from typing import List, Optional

import openai
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.compositing.concatenate import concatenate_videoclips


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BACKEND_DIR, "assets", "semana-datos")

FONDO_REEL = os.path.join(ASSETS_DIR, "fondo-reel.mp4")
FONT_PATH = os.path.join(ASSETS_DIR, "IBMPlexSans-Bold.ttf")

# Composición visual — ratios relativos al fondo (independiente de la resolución
# exacta del mp4 de fondo). Se pueden ajustar si el output queda corrido.
CLIP_WIDTH_RATIO = 0.85          # El recorte ocupa el 85% del ancho del fondo
CLIP_TOP_RATIO = 0.20            # Top del recorte (desde top del fondo)

# Subtítulos
SUB_FONT_SIZE_RATIO = 0.033      # Tamaño de la fuente ≈ 3.3% del alto (~63 px en 1920)
SUB_TOP_RATIO = 0.74             # Top del subtítulo (deja espacio entre el recorte y el logo BCR del fondo)
SUB_WIDTH_RATIO = 0.85           # Ancho del bloque de texto
SUB_COLOR = "white"
SUB_MAX_WORDS_PER_CHUNK = 7      # Si una "frase" de Whisper es muy larga, la partimos
SUB_MIN_DURATION = 0.6           # Mínimo tiempo en pantalla por chunk (para que se pueda leer)

WHISPER_MODEL = "whisper-1"
WHISPER_LANGUAGE = "es"


# ---------------------------------------------------------------------------
# Transcripción con Whisper
# ---------------------------------------------------------------------------

def _extract_audio(video_path: str, dest_path: str) -> None:
    """Extrae el audio del video a un archivo separado (formato mp3)."""
    clip = VideoFileClip(video_path)
    try:
        clip.audio.write_audiofile(dest_path, codec="libmp3lame", logger=None)
    finally:
        clip.close()


def transcribe(video_path: str) -> List[dict]:
    """Transcribe el audio del video y devuelve los segmentos de Whisper.

    Cada segmento es {"start": float, "end": float, "text": str}.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurada")
    client = openai.OpenAI(api_key=api_key)

    audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    try:
        _extract_audio(video_path, audio_path)
        with open(audio_path, "rb") as f:
            res = client.audio.transcriptions.create(
                file=f,
                model=WHISPER_MODEL,
                language=WHISPER_LANGUAGE,
                response_format="verbose_json",
            )
        # res.segments en SDK v1 es una lista de objetos pydantic; pasar a dict
        segments = []
        for seg in (res.segments or []):
            d = seg.model_dump() if hasattr(seg, "model_dump") else dict(seg)
            segments.append({
                "start": float(d.get("start", 0)),
                "end": float(d.get("end", 0)),
                "text": str(d.get("text", "")).strip(),
            })
        return segments
    finally:
        try:
            os.remove(audio_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Subtítulos — chunking y rendering
# ---------------------------------------------------------------------------

def _chunk_text(text: str, max_words: int = SUB_MAX_WORDS_PER_CHUNK) -> List[str]:
    """Si una frase es muy larga, la parte en chunks de ≤ max_words palabras."""
    words = text.split()
    if len(words) <= max_words:
        return [text]
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def _build_subtitle_clips(segments: List[dict], video_size: tuple, total_duration: float) -> List[TextClip]:
    """Construye los TextClips de subtítulos para componer sobre el video."""
    width, height = video_size
    font_size = max(28, int(height * SUB_FONT_SIZE_RATIO))
    box_width = int(width * SUB_WIDTH_RATIO)
    y_pos = int(height * SUB_TOP_RATIO)

    clips: List[TextClip] = []
    for seg in segments:
        text = (seg.get("text") or "").strip().upper()
        if not text:
            continue
        start = max(0.0, float(seg.get("start", 0)))
        end = min(total_duration, float(seg.get("end", 0)))
        if end <= start:
            continue

        chunks = _chunk_text(text)
        chunk_dur = max(SUB_MIN_DURATION, (end - start) / max(1, len(chunks)))

        for i, chunk in enumerate(chunks):
            c_start = start + i * chunk_dur
            c_end = min(total_duration, c_start + chunk_dur)
            if c_end <= c_start:
                continue
            txt = TextClip(
                text=chunk,
                font=FONT_PATH,
                font_size=font_size,
                color=SUB_COLOR,
                method="caption",
                size=(box_width, None),
                text_align="center",
            ).with_position(("center", y_pos)).with_start(c_start).with_duration(c_end - c_start)
            clips.append(txt)
    return clips


# ---------------------------------------------------------------------------
# Composición principal
# ---------------------------------------------------------------------------

def _loop_to_duration(clip, target_duration: float):
    """Loopea el clip de fondo hasta cubrir target_duration. Si ya es más largo,
    lo recorta."""
    if clip.duration >= target_duration:
        return clip.subclipped(0, target_duration)
    n = math.ceil(target_duration / clip.duration)
    return concatenate_videoclips([clip] * n).subclipped(0, target_duration)


def edit_clip(input_path: str, output_path: str) -> dict:
    """Combina el recorte input con el fondo y los subtítulos. Escribe el
    video resultante en output_path. Devuelve metadata básica del output."""
    if not os.path.exists(FONDO_REEL):
        raise RuntimeError(f"No se encontró el fondo en {FONDO_REEL}")

    bg = VideoFileClip(FONDO_REEL)
    clip = VideoFileClip(input_path)

    try:
        target_duration = clip.duration

        # 1) Resize del recorte al ancho relativo
        target_width = int(bg.w * CLIP_WIDTH_RATIO)
        clip_resized = clip.resized(width=target_width)

        # 2) Posicionar el recorte
        clip_x = (bg.w - clip_resized.w) // 2
        clip_y = int(bg.h * CLIP_TOP_RATIO)
        clip_placed = clip_resized.with_position((clip_x, clip_y))

        # 3) Loopear/recortar el fondo a la duración del clip
        bg_fit = _loop_to_duration(bg, target_duration)

        # 4) Subtítulos
        segments = transcribe(input_path)
        subtitle_clips = _build_subtitle_clips(segments, bg.size, target_duration)

        # 5) Componer
        final = CompositeVideoClip(
            [bg_fit, clip_placed] + subtitle_clips,
            size=bg.size,
        ).with_duration(target_duration).with_audio(clip.audio)

        # 6) Escribir
        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            fps=30,
            threads=4,
            logger=None,
        )

        return {
            "duration": float(target_duration),
            "subtitle_count": len(subtitle_clips),
            "size": list(bg.size),
        }
    finally:
        try:
            clip.close()
        except Exception:
            pass
        try:
            bg.close()
        except Exception:
            pass

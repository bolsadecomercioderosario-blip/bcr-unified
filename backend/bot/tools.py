"""
Tools del bot BCR — cada herramienta tiene dos partes:

1. Su definición JSON-schema en TOOL_DEFINITIONS — eso es lo que ve el LLM
   al decidir si llamarla y con qué argumentos.
2. Su implementación Python correspondiente — la ejecutamos nosotros cuando
   el LLM la pide.

execute_tool() es el dispatcher: dado el nombre y argumentos que devolvió
el modelo, llama a la función correcta y devuelve un dict serializable.

Tools registradas (bot cerrado para la Mesa Ejecutiva):
- consultar_agenda: Agenda de Compromisos (actividades de Secretaría) por rango de fechas.
- buscar_informativo / buscar_comentario_diario: búsqueda RAG sobre los vector
  stores del Informativo Semanal y de los Comentarios Diarios del mercado.
- get_precios_pizarra: precios exactos (soja/trigo/maíz) del Mercado Físico de Rosario.
- consultar_coyuntura: lee el Google Doc vivo de coyuntura que mantiene Comunicación.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from openai import OpenAI
from sqlalchemy import or_
from sqlalchemy.orm import Session

import agenda_models
from config import BOT_OPENAI_MODEL, BOT_COYUNTURA_DOC_ID

from bot.openai_vector_stores import get_vector_store_id


# Todos los timestamps que el bot devuelve al LLM (y por extensión al usuario)
# deben estar en hora local Argentina, no en UTC. Guardamos en DB como
# datetime.utcnow() (naive UTC); convertimos sólo al serializar para mostrar.
try:
    from zoneinfo import ZoneInfo
    _ART_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
except ImportError:  # pragma: no cover — Python 3.9+ tiene zoneinfo en stdlib
    _ART_TZ = None


def _utc_naive_to_art_iso(dt: datetime | None) -> str | None:
    """Naive UTC datetime → ISO string en hora Argentina (UTC-3).

    Si zoneinfo no está disponible o el datetime es None, devuelve None o el
    isoformat naive como fallback."""
    if dt is None:
        return None
    if _ART_TZ is None:
        return dt.isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_ART_TZ).isoformat()


# ---------------------------------------------------------------------------
# ToolContext: lo que reciben TODAS las tools. Cada una usa lo que le sirve;
# ignora el resto. Centralizar el contexto evita que cada nueva tool tenga
# que cambiar la firma de execute_tool ni de las que ya existen.
# ---------------------------------------------------------------------------
@dataclass
class ToolContext:
    db: Session
    openai_client: OpenAI


# ---------------------------------------------------------------------------
# Schemas en formato Responses API de OpenAI.
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "consultar_agenda",
        "description": (
            "Consulta la AGENDA DE COMPROMISOS institucionales de la Bolsa de "
            "Comercio de Rosario (BCR) en un rango de fechas — las actividades, "
            "reuniones y eventos que carga Secretaría. Usá esta herramienta para "
            "preguntas como: '¿qué actividades hay esta semana?', '¿qué compromisos "
            "tiene la BCR mañana?', '¿cuándo es la reunión con X?'. Devuelve fecha, "
            "hora, título, lugar, participantes y descripción de cada actividad."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "desde": {
                    "type": "string",
                    "description": (
                        "Fecha inicial del rango en formato YYYY-MM-DD. "
                        "Si la consulta no especifica fecha de inicio, usá la fecha de hoy."
                    ),
                },
                "hasta": {
                    "type": "string",
                    "description": (
                        "Fecha final del rango en formato YYYY-MM-DD. "
                        "Si la consulta no especifica fecha de fin, usá 7 días después de 'desde'."
                    ),
                },
                "filtro_titulo": {
                    "type": "string",
                    "description": (
                        "Texto a buscar dentro del título o descripción de las actividades. "
                        "Útil cuando la consulta menciona un evento específico (ej. 'Encuentro "
                        "de Abogados', 'BCR Innova', 'visita guiada'). Dejá vacío si la "
                        "consulta es genérica ('qué hay esta semana')."
                    ),
                },
            },
        },
    },
    {
        "type": "function",
        "name": "buscar_informativo",
        "description": (
            "Busca en el INFORMATIVO SEMANAL de la BCR — la publicación que sale "
            "todos los viernes con artículos de análisis sobre mercados, commodities, "
            "geopolítica del agro, comercio exterior, economía, política agropecuaria, "
            "novedades del sector. Usá esta tool cuando la pregunta sea sobre un "
            "tema económico/comercial/sectorial que probablemente fue analizado en "
            "el informativo: 'qué es el acuerdo UE-Mercosur', 'cómo viene la "
            "campaña de girasol', 'qué pasó con las exportaciones de soja en 2026', "
            "etc. NO confundir con los comentarios diarios (precios del día) — para "
            "esos usá buscar_comentario_diario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "Consulta a buscar en el informativo semanal.",
                },
            },
            "required": ["consulta"],
        },
    },
    {
        "type": "function",
        "name": "buscar_comentario_diario",
        "description": (
            "Busca en los COMENTARIOS DIARIOS del mercado de la BCR — reportes "
            "que se publican cada día sobre lo que pasó en el mercado físico de "
            "Rosario y en Chicago: precios de soja/maíz/trigo, movimientos del "
            "tipo de cambio, ofertas y operatoria del día. Usá esta tool para "
            "preguntas de coyuntura inmediata: 'qué pasó con la soja hoy', "
            "'cómo cerró el mercado ayer', 'qué movimientos tuvo el trigo esta "
            "semana'. Si la pregunta es de análisis o tendencia, usá "
            "buscar_informativo en su lugar."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "Consulta a buscar en los comentarios diarios.",
                },
            },
            "required": ["consulta"],
        },
    },
    {
        "type": "function",
        "name": "get_precios_pizarra",
        "description": (
            "Devuelve los precios pizarra del Mercado Físico de Rosario para "
            "soja, trigo, maíz y otros granos, con la(s) fecha(s) de los últimos "
            "días disponibles. Es DATA ESTRUCTURADA (números exactos), distinto "
            "de los comentarios narrativos. Usá esta tool cuando la pregunta "
            "pida un valor numérico concreto: 'cuánto está la soja hoy', "
            "'precio del trigo', 'cotización del maíz ayer'. Para análisis o "
            "contexto, usá buscar_comentario_diario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "producto": {
                    "type": "string",
                    "description": (
                        "Producto a consultar: 'soja', 'trigo', 'maiz', 'girasol' "
                        "o 'todos' para traer todos los disponibles."
                    ),
                },
                "fecha": {
                    "type": "string",
                    "description": (
                        "Fecha específica YYYY-MM-DD. Si se omite, devuelve la "
                        "última fecha disponible."
                    ),
                },
            },
        },
    },
    {
        "type": "function",
        "name": "consultar_coyuntura",
        "description": (
            "Consulta el DOCUMENTO VIVO DE COYUNTURA de la BCR — el documento CURADO "
            "y ACTUALIZADO que mantiene el equipo de Comunicación con la información "
            "de contexto/actualidad de mayor interés institucional del momento: "
            "mercado de granos, campaña agrícola, proyecciones de producción, "
            "estimaciones, comercio exterior, economía, política y posición de la "
            "BCR. Es una fuente de referencia amplia y confiable: consultala SIEMPRE "
            "que la pregunta toque estos temas, en combinación con el informativo o "
            "los comentarios si hace falta, y SIEMPRE antes de responder que 'no "
            "encontraste' un dato de mercado/campaña/coyuntura. Devuelve el texto del "
            "documento; respondé sólo con lo que dice."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
]


# ---------------------------------------------------------------------------
# Implementación: consultar_agenda (DB).
# ---------------------------------------------------------------------------
def _parse_iso_date(value: str | None, fallback: date) -> date:
    """Parsea una fecha YYYY-MM-DD del LLM. Si falla, devuelve el fallback —
    nunca rompemos la conversación por un parámetro mal formado."""
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


_DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _fecha_legible(iso: str) -> str:
    """'2026-08-13' -> 'Miércoles 13/8' (día de la semana + D/M). Lo calculamos
    en Python porque el LLM suele equivocar el día de la semana de una fecha."""
    try:
        d = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return iso
    return f"{_DIAS_SEMANA[d.weekday()].capitalize()} {d.day}/{d.month}"


def _activity_to_compact_dict(activity: agenda_models.Activity) -> dict[str, Any]:
    """Proyecta una Activity a un dict mínimo. Sólo campos relevantes para el
    bot — todo lo de Drive/Instagram/LinkedIn/copy es ruido para el LLM."""
    return {
        "fecha": activity.date,
        "fecha_legible": _fecha_legible(activity.date),
        "hora": activity.time,
        "titulo": activity.title,
        "descripcion": (activity.description or "").strip() or None,
        "ubicacion": (activity.location or "").strip() or None,
        "participa": (getattr(activity, "participants", "") or "").strip() or None,
        "observaciones": (activity.observations or "").strip() or None,
    }


def consultar_agenda(
    ctx: ToolContext,
    desde: str | None = None,
    hasta: str | None = None,
    filtro_titulo: str | None = None,
) -> dict[str, Any]:
    """Devuelve actividades de la BCR en el rango. Compara fechas como strings
    porque están almacenadas en YYYY-MM-DD (orden lexicográfico === cronológico).

    Sólo expone la Agenda de Compromisos: las actividades que carga Secretaría
    (origen='secretaria') y que no están archivadas. El canal 'Bot' de la
    agenda de Comunicación era de una lógica anterior y ya no se usa.
    """
    today = date.today()
    desde_d = _parse_iso_date(desde, today)
    hasta_d = _parse_iso_date(hasta, desde_d + timedelta(days=7))

    if hasta_d < desde_d:
        desde_d, hasta_d = hasta_d, desde_d

    # Sólo la Agenda de Compromisos: actividades que carga Secretaría
    # (origen='secretaria'), no archivadas.
    query = ctx.db.query(agenda_models.Activity).filter(
        agenda_models.Activity.date >= desde_d.isoformat(),
        agenda_models.Activity.date <= hasta_d.isoformat(),
        agenda_models.Activity.archived == False,  # noqa: E712 — excluir archivadas
        agenda_models.Activity.origen == "secretaria",
    )

    if filtro_titulo:
        pattern = f"%{filtro_titulo.strip()}%"
        query = query.filter(
            or_(
                agenda_models.Activity.title.ilike(pattern),
                agenda_models.Activity.description.ilike(pattern),
            )
        )

    actividades = query.order_by(
        agenda_models.Activity.date.asc(),
        agenda_models.Activity.time.asc(),
        agenda_models.Activity.order_index.asc(),
    ).all()

    return {
        "rango_consultado": {"desde": desde_d.isoformat(), "hasta": hasta_d.isoformat()},
        "filtro_titulo": filtro_titulo or None,
        "total_encontradas": len(actividades),
        "actividades": [_activity_to_compact_dict(a) for a in actividades],
    }


# ---------------------------------------------------------------------------
# Implementación: file_search wrappers (RAG sobre vector stores OpenAI).
#
# Cada wrapper hace una llamada interna a la Responses API con file_search
# apuntando a UN vector store dedicado. Devuelve el texto sintetizado que
# el modelo principal incorpora en la respuesta final al usuario.
#
# Trade-off: 1 llamada extra a OpenAI por tool invocada. Con gpt-5-mini sale
# muy barato; a cambio el modelo principal decide qué fuentes consultar en
# vez de buscar a ciegas en todos los stores juntos.
# ---------------------------------------------------------------------------
# Cuántos chunks pedir al vector store por búsqueda. El default de OpenAI
# anda en ~20; subimos porque los stores tienen cientos de chunks (la mayoría
# del PipeDream histórico) y el artículo nuevo queda fuera del top-20 a
# menudo. 50 es seguro respecto a tokens del prompt y mejora el recall.
_FILE_SEARCH_MAX_RESULTS = 50

# Peso del bonus de recencia al re-rankear chunks. 0 = solo relevancia
# semántica; 1 = solo fecha. 0.5 + decay exponencial con half-life ~31 días
# logra que un chunk de hace ~45 días pierda contra uno de hace ~12 días
# con score semántico hasta 0.4 más alto. Calibrado contra el caso real
# observado (Informativo 10/04 vs 15/05).
_RECENCY_ALPHA = 0.5
# Half-life (en días) de la curva exponencial de recencia. Más chico = más
# castigo a lo viejo. 45 es la sweet spot empírica para informativo semanal.
_RECENCY_HALF_LIFE_DAYS = 45.0

# Match para extraer fecha YYYY-MM-DD del nombre del archivo subido.
# Nuestros TXTs tienen prefijo: "2026-05-22_informativo_2244_...". Si la
# convención cambia, agregar otro patrón acá.
_FILENAME_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})_")


def _search_in_vector_store(
    ctx: ToolContext,
    vector_store_id: str | None,
    consulta: str,
    fuente_nombre: str,
    hint: str,
) -> dict[str, Any]:
    """Búsqueda directa en el vector store de OpenAI (sin loop de LLM
    interno). Antes pasábamos por client.responses.create con file_search
    como tool — eso funcionaba pero metía un segundo LLM en el medio que a
    veces decidía 'no encontré' sin usar file_search agresivamente, y a
    veces resumía mal el resultado relevante.

    Ahora llamamos directo a client.vector_stores.search() y devolvemos los
    chunks crudos al agente principal. El agente ve el texto literal de los
    documentos relevantes y los cita él mismo. Más determinístico, más
    barato (una llamada OpenAI menos por tool invocada), y más fácil de
    debuggear: si la respuesta no es buena, el problema está en el
    índice (chunks) o en la query, no en una capa de LLM intermedia.
    """
    if not vector_store_id:
        return {
            "fuente": fuente_nombre,
            "error": "vector_store_no_configurado",
            "detalle": (
                f"El vector store '{fuente_nombre}' no está configurado en este "
                "entorno (falta env var). Avisale al usuario que esa fuente no "
                "está disponible todavía y respondé con las fuentes que sí lo estén."
            ),
        }

    try:
        page = ctx.openai_client.vector_stores.search(
            vector_store_id=vector_store_id,
            query=consulta,
            max_num_results=_FILE_SEARCH_MAX_RESULTS,
            rewrite_query=True,  # que OpenAI mejore la query para vector search
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "fuente": fuente_nombre,
            "consulta": consulta,
            "error": f"fallo_search: {type(exc).__name__}: {exc}",
            "hint": hint,
        }

    items = list(getattr(page, "data", []) or [])
    if not items:
        return {
            "fuente": fuente_nombre,
            "consulta": consulta,
            "resultado": "No se encontró información en los documentos.",
            "chunks_devueltos": 0,
        }

    # Construimos chunks crudos con score y fecha (parseada del filename).
    # Después re-rankeamos con un compromiso relevancia × recencia: un chunk
    # de un mes atrás pierde frente a uno reciente con score similar. Esto
    # resuelve el caso "informativo de abril que matchea más fuerte que el
    # informativo de mayo con datos actualizados" sin depender de que el LLM
    # razone sobre fechas.
    today = date.today()
    raw_chunks: list[dict[str, Any]] = []
    for item in items:
        content_text = ""
        if getattr(item, "content", None):
            content_text = "\n".join(
                getattr(c, "text", "") for c in item.content if getattr(c, "text", "")
            )
        filename = getattr(item, "filename", None) or getattr(item, "file_id", "?")
        score = getattr(item, "score", None) or 0.0

        # Fecha desde el filename (formato YYYY-MM-DD_*).
        fecha_iso: str | None = None
        m = _FILENAME_DATE_RE.search(filename or "")
        if m:
            fecha_iso = m.group(1)

        # Bonus de recencia: decae exponencialmente desde 1.0 (hoy) con
        # half-life de _RECENCY_HALF_LIFE_DAYS. A los 45 días vale 0.5,
        # a los 90 días vale 0.25, etc. Mucho más agresivo que el decay
        # lineal a 1 año, que en la práctica no llegaba a flipear chunks.
        recency = 0.0
        if fecha_iso:
            try:
                days_old = max(0, (today - date.fromisoformat(fecha_iso)).days)
                recency = 2.0 ** (-days_old / _RECENCY_HALF_LIFE_DAYS)
            except ValueError:
                pass

        rerank_score = (1.0 - _RECENCY_ALPHA) * score + _RECENCY_ALPHA * recency

        raw_chunks.append({
            "archivo": filename,
            "fecha": fecha_iso,
            "score_semantico": round(score, 4),
            "score_recencia": round(recency, 4),
            "score_final": round(rerank_score, 4),
            "texto": content_text[:700],
        })

    # Top 8 por score final (relevancia + recencia).
    raw_chunks.sort(key=lambda c: c["score_final"], reverse=True)
    chunks = raw_chunks[:8]

    return {
        "fuente": fuente_nombre,
        "consulta": consulta,
        "chunks_devueltos": len(items),
        "ranking_nota": (
            "Los chunks vienen re-rankeados con bonus de recencia "
            f"(alpha={_RECENCY_ALPHA}). Para tu respuesta, citá los de "
            "FECHA más reciente cuando cubran el mismo tema."
        ),
        "resultado": chunks,
        "hint": hint,
    }


def buscar_informativo(ctx: ToolContext, consulta: str) -> dict[str, Any]:
    result = _search_in_vector_store(
        ctx,
        vector_store_id=get_vector_store_id(ctx.db, "informativo"),
        consulta=consulta,
        fuente_nombre="informativo_semanal",
        hint=(
            "Los documentos son artículos del Informativo Semanal de la BCR "
            "(publicación de los viernes). Cubren análisis de mercados, commodities, "
            "geopolítica del agro, comercio exterior, economía, política agropecuaria. "
            "Si encontrás fecha o número de edición, incluilo."
        ),
    )
    # Igual que en comentarios: el search es por relevancia, no por fecha.
    # Adjuntamos las últimas ediciones ingestadas para que el agente sepa
    # qué tan reciente es el corpus.
    from bot.db_models import IngestedInformativoArticle
    recientes = (
        ctx.db.query(IngestedInformativoArticle)
        .order_by(IngestedInformativoArticle.fecha.desc())
        .limit(8)
        .all()
    )
    result["recientes_por_fecha"] = [
        {
            "edicion_numero": r.edicion_numero,
            "fecha": r.fecha,
            "titulo": r.titulo,
            "seccion": r.seccion,
            "slug": r.slug,
        }
        for r in recientes
    ]
    return result


def buscar_comentario_diario(ctx: ToolContext, consulta: str) -> dict[str, Any]:
    result = _search_in_vector_store(
        ctx,
        vector_store_id=get_vector_store_id(ctx.db, "comentarios"),
        consulta=consulta,
        fuente_nombre="comentario_diario",
        hint=(
            "Los documentos son comentarios diarios del Mercado Físico de Rosario y "
            "Chicago, con precios, ofertas, operatoria del día y tipo de cambio. "
            "Si el documento trae fecha, incluila en el resumen para que se pueda citar."
        ),
    )
    # Sumamos metadata "recientes_por_fecha" leyendo directo de la DB. El
    # vector search ordena por relevancia semántica, no por fecha — sin esto
    # el agente no sabe cuál es realmente "el último" comentario disponible.
    from bot.db_models import IngestedComentario
    recientes = (
        ctx.db.query(IngestedComentario)
        .order_by(IngestedComentario.fecha.desc(), IngestedComentario.comentario_id.desc())
        .limit(5)
        .all()
    )
    result["recientes_por_fecha"] = [
        {
            "source": r.source,
            "comentario_id": r.comentario_id,
            "fecha": r.fecha,
            "url": r.url,
        }
        for r in recientes
    ]
    return result


# ---------------------------------------------------------------------------
# Implementación: get_precios_pizarra (DB — tabla que llena el scraper diario).
# ---------------------------------------------------------------------------
def get_precios_pizarra(
    ctx: ToolContext,
    producto: str | None = None,
    fecha: str | None = None,
) -> dict[str, Any]:
    """Lee la tabla precios_pizarra que mantiene el scraper.

    - Sin filtros → precios de la última fecha disponible.
    - Con `producto` → filtra por ese (case/acento-insensitive).
    - Con `fecha` → esa fecha; si no existe, devuelve 'fecha_no_disponible'
      con los datos de la fecha más reciente que sí tenemos.
    - Tabla vacía → estado 'sin_datos'.
    """
    from bot.db_models import PrecioPizarra

    base_query = ctx.db.query(PrecioPizarra)

    if producto:
        producto_norm = (
            "".join(
                ch for ch in __import__("unicodedata").normalize("NFKD", producto.strip().lower())
                if not __import__("unicodedata").combining(ch)
            )
        )
        if producto_norm != "todos":
            base_query = base_query.filter(PrecioPizarra.producto == producto_norm)

    latest_fecha_row = (
        base_query.with_entities(PrecioPizarra.fecha)
        .order_by(PrecioPizarra.fecha.desc())
        .first()
    )
    latest_fecha = latest_fecha_row[0] if latest_fecha_row else None

    if latest_fecha is None:
        return {
            "fuente": "precios_pizarra",
            "estado": "sin_datos",
            "detalle": (
                "Todavía no hay precios cargados en la base. El scraper diario "
                "corre varias veces al día; si todavía no corrió, mostrale al usuario "
                "https://www.bcr.com.ar/es/mercados/mercado-de-granos/"
                "cotizaciones/cotizaciones-locales-0."
            ),
            "consulta": {"producto": producto, "fecha": fecha},
        }

    def _serialize(rows):
        return [
            {
                "producto": r.producto,
                "fecha": r.fecha,
                "precio_ars_tn": r.precio_ars_tn,
                "actualizado_en_art": _utc_naive_to_art_iso(r.scraped_at),
            }
            for r in rows
        ]

    if fecha:
        rows = (
            base_query.filter(PrecioPizarra.fecha == fecha)
            .order_by(PrecioPizarra.producto.asc())
            .all()
        )
        if rows:
            return {
                "fuente": "precios_pizarra",
                "estado": "ok",
                "moneda": "ARS",
                "unidad": "pesos por tonelada",
                "filas": _serialize(rows),
            }
        latest_rows = (
            base_query.filter(PrecioPizarra.fecha == latest_fecha)
            .order_by(PrecioPizarra.producto.asc())
            .all()
        )
        return {
            "fuente": "precios_pizarra",
            "estado": "fecha_no_disponible",
            "fecha_pedida": fecha,
            "ultima_fecha_disponible": latest_fecha,
            "moneda": "ARS",
            "unidad": "pesos por tonelada",
            "filas": _serialize(latest_rows),
            "detalle": (
                f"No hay datos para {fecha}. Devolvemos los precios de la "
                f"última fecha que sí tenemos: {latest_fecha}. El agente debe "
                "decirle eso al usuario explícitamente."
            ),
        }

    rows = (
        base_query.filter(PrecioPizarra.fecha == latest_fecha)
        .order_by(PrecioPizarra.producto.asc())
        .all()
    )
    return {
        "fuente": "precios_pizarra",
        "estado": "ok",
        "moneda": "ARS",
        "unidad": "pesos por tonelada",
        "filas": _serialize(rows),
    }


# ---------------------------------------------------------------------------
# Implementación: consultar_coyuntura (Google Doc vivo que mantiene Comunicación).
# Lee el texto exportado del doc público, con una cachecita de 5 min para que los
# cambios se reflejen rápido sin pegarle a Google en cada consulta. Si el fetch
# falla, cae al último texto cacheado (si hay).
# ---------------------------------------------------------------------------
_COYUNTURA_CACHE: dict[str, Any] = {"text": None, "fetched_at": 0.0}
_COYUNTURA_TTL_S = 300


def _fetch_coyuntura_doc() -> str | None:
    doc_id = (BOT_COYUNTURA_DOC_ID or "").strip()
    if not doc_id:
        return None
    now = time.time()
    if _COYUNTURA_CACHE["text"] is not None and (now - _COYUNTURA_CACHE["fetched_at"]) < _COYUNTURA_TTL_S:
        return _COYUNTURA_CACHE["text"]
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        text = (resp.text or "").replace("﻿", "").strip()
        if text:
            _COYUNTURA_CACHE["text"] = text
            _COYUNTURA_CACHE["fetched_at"] = now
        return text or _COYUNTURA_CACHE["text"]
    except Exception:
        return _COYUNTURA_CACHE["text"]


def consultar_coyuntura(ctx: ToolContext) -> dict[str, Any]:
    text = _fetch_coyuntura_doc()
    if not text:
        return {
            "fuente": "coyuntura",
            "error": "documento_no_disponible",
            "detalle": (
                "No pude leer el documento de coyuntura (no configurado o no "
                "accesible). Decile al usuario que esa información no está "
                "disponible en este momento."
            ),
        }
    MAX = 30000  # ~7500 tokens; cubre un doc largo sin inflar de más el prompt
    return {
        "fuente": "coyuntura",
        "descripcion": (
            "Documento vivo de temas de coyuntura de interés, mantenido por el "
            "equipo de Comunicación de la BCR."
        ),
        "contenido": text[:MAX],
        "truncado": len(text) > MAX,
    }


# ---------------------------------------------------------------------------
# Dispatcher.
# ---------------------------------------------------------------------------
_TOOL_REGISTRY = {
    "consultar_agenda": consultar_agenda,
    "buscar_informativo": buscar_informativo,
    "buscar_comentario_diario": buscar_comentario_diario,
    "get_precios_pizarra": get_precios_pizarra,
    "consultar_coyuntura": consultar_coyuntura,
}


def execute_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Llama la tool por nombre. Si no existe o tira excepción, devuelve un
    dict con 'error' que el LLM puede leer y comunicar al usuario sin romper."""
    func = _TOOL_REGISTRY.get(name)
    if func is None:
        return {"error": f"tool_desconocida: {name}"}
    try:
        return func(ctx=ctx, **arguments)
    except TypeError as exc:
        return {"error": f"argumentos_invalidos: {exc}"}
    except Exception as exc:  # noqa: BLE001 — capturamos todo para no romper la conversación
        return {"error": f"fallo_tool: {type(exc).__name__}: {exc}"}

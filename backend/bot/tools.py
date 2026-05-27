"""
Tools del bot BCR — cada herramienta tiene dos partes:

1. Su definición JSON-schema en TOOL_DEFINITIONS — eso es lo que ve el LLM
   al decidir si llamarla y con qué argumentos.
2. Su implementación Python correspondiente — la ejecutamos nosotros cuando
   el LLM la pide.

execute_tool() es el dispatcher: dado el nombre y argumentos que devolvió
el modelo, llama a la función correcta y devuelve un dict serializable.

Tools registradas:
- consultar_agenda: lee tabla activities con filtros de fecha y título.
- buscar_institucional / buscar_informativo / buscar_comentario_diario:
  wrappers de file_search sobre los 3 vector stores OpenAI. Cada uno hace
  una llamada interna a la Responses API contra su VS dedicado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy import or_
from sqlalchemy.orm import Session

import agenda_models
from config import BOT_OPENAI_MODEL

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
            "Consulta la agenda de actividades, eventos, encuentros y capacitaciones "
            "de la Bolsa de Comercio de Rosario (BCR) en un rango de fechas. "
            "Usá esta herramienta para preguntas como: '¿qué actividades hay esta "
            "semana?', '¿qué eventos tiene BCR mañana?', '¿cuándo es el Encuentro "
            "de Abogados?', '¿hay alguna capacitación de BCRcapacita este mes?'. "
            "Devuelve título, fecha, hora, ubicación y descripción de cada actividad "
            "encontrada."
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
        "name": "buscar_institucional",
        "description": (
            "Busca en la base de conocimiento INSTITUCIONAL de la BCR. Contiene info "
            "sobre: qué es la BCR, historia, autoridades, sedes y contacto general; "
            "los mercados (Mercado Físico de Granos, A3, MAV, Rosgan); las cámaras "
            "arbitrales (Cereales, CAAVS, Tribunal General); BCRlabs (laboratorios); "
            "Dirección de Información y Estudios Económicos; BCRdigital, BCRinnova, "
            "BCRcapacita, BCRcultura; Fundación BCR; Centro de Convenciones; Oficina "
            "de Asociados; museo y biblioteca. Usá esta tool para preguntas tipo "
            "'¿qué es BCRlabs?', '¿quién es el presidente?', '¿cómo me asocio?', "
            "'¿dónde queda la BCR?'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": (
                        "Consulta a buscar, idealmente reformulada para maximizar el match "
                        "con los documentos (sustantivos clave > frase coloquial)."
                    ),
                },
            },
            "required": ["consulta"],
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
        "name": "get_estimaciones_gea",
        "description": (
            "Devuelve las estimaciones de producción nacional de GEA (Guía "
            "Estratégica para el Agro de la BCR) para soja, trigo y maíz: área "
            "sembrada, rinde y producción de la campaña vigente y la anterior. "
            "Es DATA ESTRUCTURADA. Usá esta tool cuando la pregunta sea sobre "
            "cuánto se va a producir, área sembrada, rindes proyectados a nivel "
            "nacional. Para análisis o detalle del informe, usá buscar_informe_gea."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cultivo": {
                    "type": "string",
                    "description": (
                        "Cultivo a consultar: 'soja', 'trigo', 'maiz' o 'todos'."
                    ),
                },
            },
        },
    },
    {
        "type": "function",
        "name": "buscar_informe_gea",
        "description": (
            "Busca en los INFORMES DE ESTIMACIÓN NACIONAL DE PRODUCCIÓN de GEA. "
            "Son reportes mensuales firmados (ej. por Cristián Russo) con análisis "
            "técnico de campañas agrícolas: condiciones climáticas, reservas de "
            "agua, decisiones de siembra, ajustes de producción, etc. Usá esta "
            "tool para preguntas sobre el porqué de los cambios en estimaciones "
            "('por qué cae la siembra de trigo', 'cómo afectaron las lluvias a "
            "la soja'), o cuando la pregunta pida narrativa/explicación. Para "
            "los números puros usá get_estimaciones_gea."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "Consulta a buscar en los informes GEA.",
                },
            },
            "required": ["consulta"],
        },
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


def _activity_to_compact_dict(activity: agenda_models.Activity) -> dict[str, Any]:
    """Proyecta una Activity a un dict mínimo. Sólo campos relevantes para el
    bot — todo lo de Drive/Instagram/LinkedIn/copy es ruido para el LLM."""
    return {
        "fecha": activity.date,
        "hora": activity.time,
        "titulo": activity.title,
        "descripcion": (activity.description or "").strip() or None,
        "ubicacion": (activity.location or "").strip() or None,
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

    Sólo expone al bot las actividades con el canal 'Bot' tildado en la
    agenda (channels contiene "Bot"). El filtrado se hace en Python para
    ser DB-agnóstico (JSON contains varía entre Postgres y SQLite); con el
    tamaño de la agenda (decenas a cientos de filas) no hay riesgo de
    performance.
    """
    today = date.today()
    desde_d = _parse_iso_date(desde, today)
    hasta_d = _parse_iso_date(hasta, desde_d + timedelta(days=7))

    if hasta_d < desde_d:
        desde_d, hasta_d = hasta_d, desde_d

    query = ctx.db.query(agenda_models.Activity).filter(
        agenda_models.Activity.date >= desde_d.isoformat(),
        agenda_models.Activity.date <= hasta_d.isoformat(),
    )

    if filtro_titulo:
        pattern = f"%{filtro_titulo.strip()}%"
        query = query.filter(
            or_(
                agenda_models.Activity.title.ilike(pattern),
                agenda_models.Activity.description.ilike(pattern),
            )
        )

    all_in_range = query.order_by(
        agenda_models.Activity.date.asc(),
        agenda_models.Activity.time.asc(),
        agenda_models.Activity.order_index.asc(),
    ).all()

    # Solo actividades marcadas para el Bot.
    visible = [a for a in all_in_range if "Bot" in (a.channels or [])]

    return {
        "rango_consultado": {"desde": desde_d.isoformat(), "hasta": hasta_d.isoformat()},
        "filtro_titulo": filtro_titulo or None,
        "total_encontradas": len(visible),
        "total_en_rango_sin_filtro_bot": len(all_in_range),
        "actividades": [_activity_to_compact_dict(a) for a in visible],
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

    # Devolvemos los chunks crudos, ordenados por score descendente que ya
    # viene del API. Truncamos cada chunk a ~700 chars para no inflar el
    # prompt del agente principal con texto repetido (el header de cada TXT
    # se repite igual entre chunks del mismo archivo).
    chunks: list[dict[str, Any]] = []
    for item in items[:8]:  # top 8 al agente — suficiente para sintetizar respuesta
        content_text = ""
        if getattr(item, "content", None):
            content_text = "\n".join(
                getattr(c, "text", "") for c in item.content if getattr(c, "text", "")
            )
        chunks.append({
            "archivo": getattr(item, "filename", None) or getattr(item, "file_id", "?"),
            "score": getattr(item, "score", None),
            "texto": content_text[:700],
        })

    return {
        "fuente": fuente_nombre,
        "consulta": consulta,
        "chunks_devueltos": len(items),
        "resultado": chunks,
        "hint": hint,
    }


def buscar_institucional(ctx: ToolContext, consulta: str) -> dict[str, Any]:
    return _search_in_vector_store(
        ctx,
        vector_store_id=get_vector_store_id(ctx.db, "institucional"),
        consulta=consulta,
        fuente_nombre="institucional",
        hint=(
            "Los documentos cubren áreas, autoridades, mercados (Físico de Granos, "
            "A3, MAV, Rosgan), cámaras arbitrales, BCRlabs, BCRdigital, BCRinnova, "
            "BCRcapacita, BCRcultura, Fundación BCR, Centro de Convenciones, Oficina "
            "de Asociados, museo, biblioteca, contactos institucionales."
        ),
    )


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


def buscar_informe_gea(ctx: ToolContext, consulta: str) -> dict[str, Any]:
    return _search_in_vector_store(
        ctx,
        vector_store_id=get_vector_store_id(ctx.db, "gea"),
        consulta=consulta,
        fuente_nombre="informe_gea",
        hint=(
            "Los documentos son informes mensuales de Estimación Nacional de "
            "Producción de la Guía Estratégica para el Agro (GEA) de la BCR. "
            "Cubren campañas de soja, trigo, maíz, girasol y otros, con análisis "
            "de área sembrada, rinde, producción, clima, reservas de agua, decisiones "
            "de siembra. Si el documento trae fecha del informe o autor (ej. "
            "Cristián Russo), incluilos en el resumen."
        ),
    )


# ---------------------------------------------------------------------------
# Implementación: data estructurada (placeholders hasta que existan scrapers).
#
# get_precios_pizarra y get_estimaciones_gea van a leer tablas que todavía no
# creamos — los scrapers de chunks 3.1 y 3.5 las van a poblar. Por ahora
# devuelven un dict "datos_no_disponibles_aun" para que el agente pueda
# avisar al usuario sin romper.
# ---------------------------------------------------------------------------
def get_precios_pizarra(
    ctx: ToolContext,
    producto: str | None = None,
    fecha: str | None = None,
) -> dict[str, Any]:
    """Lee la tabla precios_pizarra que mantiene el scraper (chunk 3.1).

    Comportamiento clave:
    - Sin filtros → devuelve los precios de la última fecha disponible.
    - Con `producto` → filtra por ese (case/acento-insensitive).
    - Con `fecha` → trae esa fecha. Si NO existe esa fecha en la base,
      devuelve estado 'fecha_no_disponible' y a la vez incluye los datos
      de la fecha más reciente que sí tenemos. Eso le permite al agente
      decir "no hay del 26/05; el último cargado es del 22/05" en una
      sola pasada, sin hacer otra tool call.

    Si la tabla está vacía (scraper nunca corrió), devuelve estado especial.
    """
    # Import local para evitar ciclo bot.tools ↔ bot.db_models al cargar el
    # módulo desde el scraper.
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

    # Última fecha disponible en la base (con los filtros de producto aplicados).
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
                # Mostramos el "scraped_at" en hora Argentina, no UTC, para
                # que el agente no diga cosas como "actualizado a las 13:30"
                # cuando son las 10:30 ART (offset -3h).
                "actualizado_en_art": _utc_naive_to_art_iso(r.scraped_at),
            }
            for r in rows
        ]

    # Caso: pidieron una fecha específica.
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
        # No hay datos para esa fecha — devolvemos lo más reciente que tengamos
        # como contexto, para que el agente lo cite en su respuesta.
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

    # Sin fecha explícita: devolvemos la fecha más reciente.
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


def get_estimaciones_gea(
    ctx: ToolContext,
    cultivo: str | None = None,
) -> dict[str, Any]:
    """Lee la tabla estimaciones_gea que mantiene el scraper de GEA (chunk 3.5).

    - Sin filtros → trae todas las filas (todas las campañas para todos los cultivos)
    - Con `cultivo` ('soja', 'trigo', 'maiz', 'girasol') → filtra por ese.
      Acepta también acentos ('maíz' se normaliza a 'maiz').

    Si la tabla está vacía, devuelve estado especial para que el agente
    pueda avisar al usuario sin alucinar números.
    """
    from bot.db_models import EstimacionGea

    query = ctx.db.query(EstimacionGea)
    if cultivo:
        cultivo_norm = (
            "".join(
                ch for ch in __import__("unicodedata").normalize("NFKD", cultivo.strip().lower())
                if not __import__("unicodedata").combining(ch)
            )
        )
        if cultivo_norm != "todos":
            query = query.filter(EstimacionGea.cultivo == cultivo_norm)

    rows = query.order_by(
        EstimacionGea.cultivo.asc(),
        EstimacionGea.campania.desc(),
    ).all()

    if not rows:
        return {
            "fuente": "estimaciones_gea",
            "estado": "sin_datos",
            "detalle": (
                "Todavía no hay estimaciones de GEA cargadas en la base. El scraper "
                "semanal va a llenar la tabla automáticamente. Mientras tanto, "
                "sugerile al usuario que mire https://www.bcr.com.ar/es/mercados/gea."
            ),
            "consulta": {"cultivo": cultivo},
        }

    return {
        "fuente": "estimaciones_gea",
        "estado": "ok",
        "unidades": {
            "area_sembrada": "millones de hectáreas",
            "rinde": "quintales por hectárea",
            "produccion": "millones de toneladas",
        },
        "filas": [
            {
                "cultivo": r.cultivo,
                "campania": r.campania,
                "area_sembrada_mha": r.area_sembrada_mha,
                "rinde_qq_ha": r.rinde_qq_ha,
                "produccion_mtn": r.produccion_mtn,
                "actualizado_en_art": _utc_naive_to_art_iso(r.scraped_at),
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Dispatcher.
# ---------------------------------------------------------------------------
_TOOL_REGISTRY = {
    "consultar_agenda": consultar_agenda,
    "buscar_institucional": buscar_institucional,
    "buscar_informativo": buscar_informativo,
    "buscar_comentario_diario": buscar_comentario_diario,
    "buscar_informe_gea": buscar_informe_gea,
    "get_precios_pizarra": get_precios_pizarra,
    "get_estimaciones_gea": get_estimaciones_gea,
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

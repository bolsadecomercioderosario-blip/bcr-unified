"""
Tools del bot BCR — cada herramienta tiene dos partes:

1. Su definición JSON-schema en TOOL_DEFINITIONS — eso es lo que ve el LLM
   al decidir si llamarla y con qué argumentos.
2. Su implementación Python correspondiente — la ejecutamos nosotros cuando
   el LLM la pide.

execute_tool() es el dispatcher: dado el nombre y argumentos que devolvió
el modelo, llama a la función correcta y devuelve un dict serializable.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

import agenda_models


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
]


# ---------------------------------------------------------------------------
# Implementaciones.
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
    db: Session,
    desde: str | None = None,
    hasta: str | None = None,
    filtro_titulo: str | None = None,
) -> dict[str, Any]:
    """Devuelve actividades de la BCR en el rango. Compara fechas como strings
    porque están almacenadas en YYYY-MM-DD (orden lexicográfico === cronológico)."""
    today = date.today()
    desde_d = _parse_iso_date(desde, today)
    hasta_d = _parse_iso_date(hasta, desde_d + timedelta(days=7))

    if hasta_d < desde_d:
        desde_d, hasta_d = hasta_d, desde_d

    query = db.query(agenda_models.Activity).filter(
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

    activities = query.order_by(
        agenda_models.Activity.date.asc(),
        agenda_models.Activity.time.asc(),
        agenda_models.Activity.order_index.asc(),
    ).all()

    return {
        "rango_consultado": {"desde": desde_d.isoformat(), "hasta": hasta_d.isoformat()},
        "filtro_titulo": filtro_titulo or None,
        "total_encontradas": len(activities),
        "actividades": [_activity_to_compact_dict(a) for a in activities],
    }


# ---------------------------------------------------------------------------
# Dispatcher.
# ---------------------------------------------------------------------------
_TOOL_REGISTRY = {
    "consultar_agenda": consultar_agenda,
}


def execute_tool(name: str, arguments: dict[str, Any], db: Session) -> dict[str, Any]:
    """Llama la tool por nombre. Si no existe o tira excepción, devuelve un
    dict con 'error' que el LLM puede leer y comunicar al usuario sin romper."""
    func = _TOOL_REGISTRY.get(name)
    if func is None:
        return {"error": f"tool_desconocida: {name}"}
    try:
        return func(db=db, **arguments)
    except TypeError as exc:
        return {"error": f"argumentos_invalidos: {exc}"}
    except Exception as exc:  # noqa: BLE001 — queremos capturar todo para no romper la conversación
        return {"error": f"fallo_tool: {type(exc).__name__}: {exc}"}

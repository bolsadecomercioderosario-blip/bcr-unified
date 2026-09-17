"""
Handlers del menú interactivo del bot (WhatsApp list-picker).

Cuando el usuario toca una opción del menú, en vez de correr el agente completo
(lento y con formato variable), ruteamos a un handler propio que arma una
respuesta corta y consistente. Los rápidos leen la DB directo; GEA y Conectados
hacen una búsqueda en su vector store + un resumen breve del LLM.

Cada respuesta termina con una pregunta de seguimiento propia del tópico.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_

import agenda_models
from bot.db_models import (
    IngestedConectado,
    IngestedGeaReport,
    IngestedInformativoArticle,
    PrecioPizarra,
)
from bot.openai_vector_stores import get_vector_store_id

_ARG = timedelta(hours=3)  # ART = UTC-3 (Argentina no tiene DST)
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _now_art() -> datetime:
    return datetime.utcnow() - _ARG


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# Texto (normalizado) que llega al tocar cada opción de la lista, o el número
# del fallback de texto. Match EXACTO para no interceptar consultas libres.
# Al tocar una opción de la lista, Twilio manda el `id` del ítem (no el título).
# Incluimos el id, el título y el número (del fallback de texto). Match EXACTO.
_OPTIONS: dict[str, set] = {
    "agenda": {"agenda", "agenda de compromisos", "1"},
    "precios": {"precios", "precios y mercado", "precios de pizarra", "precios de pizarra / comentarios de mercado", "2"},
    "informativo": {"informativo", "informativo semanal", "3"},
    "gea": {"gea", "estimaciones y clima", "estimaciones y clima (gea)", "4"},
    "asuntos": {"asuntos", "asuntos publicos", "agenda de asuntos publicos", "5"},
    "conectados": {"conectados", "que hizo la bcr", "que hizo la bcr (conectados)", "6"},
}


def match_option(body: str) -> Optional[str]:
    t = _norm(body)
    for opt, keys in _OPTIONS.items():
        if t in keys:
            return opt
    return None


def _no_autolink(text: str) -> str:
    """Evita que WhatsApp convierta en link cosas tipo 'Bs.As' (lee '.as' como
    dominio). Inserta un carácter invisible (U+200B) entre un punto y la letra
    que le sigue sin espacio. No afecta texto normal (que lleva '. ' con espacio)."""
    return re.sub(r"\.(?=[A-Za-z])", ".​", text or "")


# --- Helpers de fecha ------------------------------------------------------
def _fecha_dia(d: date) -> str:
    return f"{_DIAS[d.weekday()]} {d.day}/{d.month}"


def _fecha_dm(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d.day}/{d.month}"
    except (ValueError, TypeError):
        return iso or ""


def _fecha_dm_y(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
        return f"{d.day}/{d.month}/{d.year}"
    except (ValueError, TypeError):
        return iso or ""


# --- OpenAI (para GEA y Conectados) ----------------------------------------
def _client():
    from openai import OpenAI
    from config import BOT_OPENAI_API_KEY
    if not BOT_OPENAI_API_KEY:
        return None
    return OpenAI(api_key=BOT_OPENAI_API_KEY, timeout=30.0, max_retries=1)


def _vs_text(vs_id: Optional[str], query: str, max_results: int = 8) -> Optional[str]:
    """Devuelve el texto de los chunks más relevantes de un vector store."""
    if not vs_id:
        return None
    c = _client()
    if not c:
        return None
    try:
        page = c.vector_stores.search(
            vector_store_id=vs_id, query=query, max_num_results=max_results, rewrite_query=True,
        )
    except Exception:  # noqa: BLE001
        return None
    chunks = []
    for item in getattr(page, "data", []) or []:
        if getattr(item, "content", None):
            chunks.append("\n".join(getattr(x, "text", "") for x in item.content if getattr(x, "text", "")))
    txt = "\n\n".join(chunks).strip()
    return txt[:6000] or None


def _llm(prompt: str) -> Optional[str]:
    c = _client()
    if not c:
        return None
    from config import BOT_OPENAI_MODEL
    try:
        r = c.responses.create(model=BOT_OPENAI_MODEL, input=prompt)
        return (getattr(r, "output_text", "") or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


# --- 1) Agenda de Compromisos (hoy y mañana) -------------------------------
def _fmt_hora(a) -> str:
    t = (a.time or "").strip()
    if t in ("", "00:00", "A definir"):
        return "A definir"
    if t == "Sin horario":
        return "Todo el día"
    if a.end_time and a.end_time.strip() not in ("", "00:00"):
        return f"{t} a {a.end_time.strip()}"
    return t


def _agenda(db) -> str:
    now = _now_art()
    today, manana = now.date(), now.date() + timedelta(days=1)
    hhmm = now.strftime("%H:%M")
    acts = db.query(agenda_models.Activity).filter(
        agenda_models.Activity.is_custom == False,  # noqa: E712
        agenda_models.Activity.archived == False,   # noqa: E712
        agenda_models.Activity.date.in_([today.isoformat(), manana.isoformat()]),
        or_(agenda_models.Activity.origen == "secretaria",
            agenda_models.Activity.me_estado == "aprobada"),
    ).order_by(
        agenda_models.Activity.date.asc(),
        agenda_models.Activity.time.asc(),
        agenda_models.Activity.order_index.asc(),
    ).all()

    def keep_today(a) -> bool:
        t = (a.time or "").strip()
        if t in ("", "00:00", "A definir", "Sin horario"):
            return True
        return t >= hhmm

    hoy = [a for a in acts if a.date == today.isoformat() and keep_today(a)]
    man = [a for a in acts if a.date == manana.isoformat()]

    if not hoy and not man:
        return ("No hay actividades cargadas en la Agenda de Compromisos para hoy ni mañana.\n\n"
                "¿Querés ver la Agenda del resto de la semana o de la semana próxima?")

    def blk(items) -> str:
        if not items:
            return "_Sin actividades._"
        out = []
        for a in items:
            line = f"- {_fmt_hora(a)} · {a.title}"
            extra = []
            if (a.location or "").strip():
                extra.append(f"Lugar: {a.location.strip()}")
            parts = (getattr(a, "participants", "") or "").strip()
            if parts:
                extra.append(f"Participa: {parts}")
            if extra:
                line += "\n  " + " — ".join(extra)
            out.append(line)
        return "\n".join(out)

    return (
        "Los miembros de la Mesa Ejecutiva que quieran participar de alguna de las "
        "actividades pueden comunicarse con la Secretaría de Presidencia (Daniel Vicente) "
        "para coordinar su participación.\n\n"
        "Estas son las actividades de la Agenda de Compromisos para hoy y mañana:\n\n"
        f"*Hoy — {_fecha_dia(today)}*\n{blk(hoy)}\n\n"
        f"*Mañana — {_fecha_dia(manana)}*\n{blk(man)}\n\n"
        "¿Querés ver la Agenda del resto de la semana o de la semana próxima?"
    )


# --- 2) Precios de pizarra -------------------------------------------------
_ORD = {"trigo": 0, "maiz": 1, "maíz": 1, "girasol": 2, "soja": 3, "sorgo": 4, "cebada": 5}
_CAP = {"trigo": "Trigo", "maiz": "Maíz", "maíz": "Maíz", "girasol": "Girasol",
        "soja": "Soja", "sorgo": "Sorgo", "cebada": "Cebada"}


def _fmt_ars(v) -> str:
    try:
        return "$" + f"{int(round(float(v))):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "-"


def _precios(db) -> str:
    row = db.query(PrecioPizarra.fecha).order_by(PrecioPizarra.fecha.desc()).first()
    if not row:
        return "Todavía no hay precios de pizarra cargados. Probá de nuevo más tarde."
    fecha = row[0]
    rows = db.query(PrecioPizarra).filter(PrecioPizarra.fecha == fecha).all()
    rows.sort(key=lambda r: _ORD.get((r.producto or "").lower(), 9))
    lineas = [f"- *{_CAP.get((r.producto or '').lower(), (r.producto or '').title())}*: {_fmt_ars(r.precio_ars_tn)}"
              for r in rows]
    return (
        f"Precios de pizarra (Rosario) — {_fecha_dm(fecha)}:\n\n"
        + "\n".join(lineas)
        + "\n\n¿Querés el comentario diario del mercado?"
    )


# --- 3) Informativo Semanal ------------------------------------------------
def _informativo(db) -> str:
    latest = (db.query(IngestedInformativoArticle)
              .order_by(IngestedInformativoArticle.fecha.desc(),
                        IngestedInformativoArticle.edicion_numero.desc())
              .first())
    if not latest:
        return "Todavía no hay Informativo Semanal cargado."
    num = latest.edicion_numero
    if num:
        arts = (db.query(IngestedInformativoArticle)
                .filter(IngestedInformativoArticle.edicion_numero == num)
                .order_by(IngestedInformativoArticle.id.asc()).all())
    else:
        arts = (db.query(IngestedInformativoArticle)
                .filter(IngestedInformativoArticle.fecha == latest.fecha)
                .order_by(IngestedInformativoArticle.id.asc()).all())
    encabezado = ("El último Informativo Semanal"
                  + (f" N° {num}" if num else "")
                  + f" ({_fecha_dm_y(latest.fecha)}) incluyó los siguientes informes:")
    lineas = [f"- {(a.titulo or '').strip()}" for a in arts if (a.titulo or '').strip()]
    return encabezado + "\n\n" + "\n".join(lineas) + "\n\n¿Querés que profundice en alguno de estos informes?"


# --- 4) GEA (resumen del último informe) -----------------------------------
def _gea(db) -> str:
    rep = (db.query(IngestedGeaReport)
           .order_by(IngestedGeaReport.fecha.desc(), IngestedGeaReport.ingested_at.desc())
           .first())
    cierre = "\n\n¿Querés el detalle de estimaciones por cultivo o el seguimiento de clima?"
    if not rep:
        return "Todavía no hay informes de GEA cargados." + cierre
    texto = _vs_text(get_vector_store_id(db, "gea"), rep.titulo or "informe GEA")
    if texto:
        resumen = _llm(
            "Resumí en UN SOLO párrafo (máx. 6 líneas), en español rioplatense, el último informe "
            "de GEA (Guía Estratégica para el Agro de la BCR). Empezá con 'El último informe de GEA'. "
            "No uses listas ni títulos ni viñetas. Contenido:\n\n" + texto
        )
        if resumen:
            return resumen + cierre
    return f"El último informe de GEA disponible es «{rep.titulo}» ({_fecha_dm(rep.fecha)})." + cierre


# --- 5) Asuntos Públicos (pregunta qué tema) -------------------------------
def _asuntos(db) -> str:
    return (
        "La Agenda de Asuntos Públicos cubre varios temas estratégicos "
        "(por ejemplo: Hidrovía / Vía Navegable Troncal, Retenciones / DEX, Financiamiento de "
        "obra pública, Accesos viales, Mercosur-UE, Biodiésel).\n\n"
        "¿Sobre qué tema querés conocer la posición institucional y el estado actual? Escribime el tema."
    )


# --- 6) Conectados (títulos del último) ------------------------------------
def _conectados(db) -> str:
    latest = db.query(IngestedConectado).order_by(IngestedConectado.fecha.desc()).first()
    if not latest:
        return "Todavía no hay newsletters Conectados cargados."
    label = (latest.titulo or f"Conectados {_fecha_dm(latest.fecha)}").strip()
    cierre = "\n\n¿Querés que te cuente más sobre alguno?"
    texto = _vs_text(get_vector_store_id(db, "conectados"), (latest.titulo or "Conectados"))
    if texto:
        titulos = _llm(
            "Del siguiente contenido del último newsletter Conectados de la BCR, listá SOLO los "
            "títulos de cada nota/bloque, uno por línea con guion (-). Sin resumen ni texto adicional.\n\n"
            + texto
        )
        if titulos:
            return f"El último {label} incluyó:\n\n{titulos}{cierre}"
    return f"El último {label} está cargado, pero no pude leer los títulos en este momento." + cierre


_HANDLERS = {
    "agenda": _agenda,
    "precios": _precios,
    "informativo": _informativo,
    "gea": _gea,
    "asuntos": _asuntos,
    "conectados": _conectados,
}


def handle(option: str, db) -> str:
    return _no_autolink(_HANDLERS[option](db))

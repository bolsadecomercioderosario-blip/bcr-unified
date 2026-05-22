"""
Scraper de GEA (Guía Estratégica para el Agro) de la BCR.

Dos surfaces independientes:

1. PANEL (data estructurada): /es/mercados/gea trae arriba un panel con
   Trigo/Maíz/Soja × (Area Sembrada, Rinde, Producción) × (campaña vigente
   + anterior). Eso va a la tabla estimaciones_gea (upsert por (cultivo,
   campania)). Lo consulta directo la tool get_estimaciones_gea.

2. INFORMES (RAG): /estimaciones-nacionales-de-produccion/estimaciones-anteriores
   lista los informes mensuales firmados (ej. por Cristián Russo). Cada uno
   tiene un slug descriptivo en la URL. Se suben como TXT al vector store
   "Informes GEA" (auto-bootstrap igual que comentarios/informativo).
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from sqlalchemy.orm import Session

from config import BOT_OPENAI_API_KEY

from bot.db_models import EstimacionGea, IngestedGeaReport
from bot.openai_vector_stores import ensure_vector_store_id, upload_text_file


_BASE = "https://www.bcr.com.ar"
_PANEL_URL = f"{_BASE}/es/mercados/gea"
_INFORMES_URL = (
    f"{_BASE}/es/mercados/gea/estimaciones-nacionales-de-produccion/"
    "estimaciones-anteriores"
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"}
_HTTP_TIMEOUT = 30
_POLITE_DELAY_S = 1.5

# Cap del backfill mensual de informes.
_DEFAULT_INFORMES_MAX_PAGES = 1
_DEFAULT_INFORMES_MAX_UPLOAD = 12


# ---------------------------------------------------------------------------
# Panel parser.
# ---------------------------------------------------------------------------
_CULTIVOS_KNOWN = {
    "trigo": "trigo",
    "maíz": "maiz",
    "maiz": "maiz",
    "soja": "soja",
    "girasol": "girasol",
    "sorgo": "sorgo",
    "cebada": "cebada",
}

# Orden de las unidades dentro de cada campaña (siempre el mismo en el sitio).
# Cada unit_label apunta al slot del dict de salida.
_UNIT_TO_SLOT = (
    ("MILLONES HA", "area_sembrada_mha"),
    ("MILL. HA", "area_sembrada_mha"),
    ("MILL HA", "area_sembrada_mha"),
    ("QQ/HA", "rinde_qq_ha"),
    ("QUINTALES", "rinde_qq_ha"),
    ("MILLONES TN", "produccion_mtn"),
    ("MILL. TN", "produccion_mtn"),
    ("MILL TN", "produccion_mtn"),
    ("MT", "produccion_mtn"),
)

# Headers que aparecen en el panel y queremos ignorar al tokenizar.
_IGNORE_TOKENS = {
    "estimaciones de producción",
    "estimaciones de produccion",
    "area sembrada",
    "área sembrada",
    "rinde",
    "produccion",
    "producción",
}


def _parse_panel_text(text: str) -> list[dict[str, Any]]:
    """Parser tolerante: tokeniza por '|' (BeautifulSoup separa elementos así
    cuando le pasamos sep='|') y va armando filas a medida que detecta
    cultivo → campaña → (número?, unidad) × 3.

    Soporta que rinde o producción estén vacíos (caso típico de la campaña
    siguiente todavía sin sembrar)."""
    tokens = [t.strip() for t in text.split("|") if t.strip()]

    results: list[dict[str, Any]] = []
    current_cultivo: str | None = None
    current_campania: str | None = None
    current_row: dict[str, Any] | None = None
    pending_value: float | None = None

    def flush() -> None:
        nonlocal current_row
        if current_row is not None:
            results.append(current_row)
        current_row = None

    for raw in tokens:
        lower = raw.lower()
        if lower in _IGNORE_TOKENS:
            continue

        # ¿Cultivo?
        if lower in _CULTIVOS_KNOWN:
            flush()
            current_cultivo = _CULTIVOS_KNOWN[lower]
            current_campania = None
            pending_value = None
            continue

        # ¿Campaña YYYY/YYYY o YYYY/YY?
        m_camp = re.match(r"^(\d{4})/(\d{2,4})$", raw)
        if m_camp:
            flush()
            current_campania = raw
            pending_value = None
            if current_cultivo:
                current_row = {
                    "cultivo": current_cultivo,
                    "campania": current_campania,
                    "area_sembrada_mha": None,
                    "rinde_qq_ha": None,
                    "produccion_mtn": None,
                }
            continue

        # ¿Número solo (ej. "6,6")?
        m_num = re.match(r"^-?\d+(?:[.,]\d+)?$", raw)
        if m_num:
            try:
                pending_value = float(raw.replace(",", "."))
            except ValueError:
                pending_value = None
            continue

        # ¿Unidad? Si veo unidad y current_row activo, asigno (pending o None).
        upper = raw.upper()
        for unit_label, slot in _UNIT_TO_SLOT:
            if unit_label in upper:
                if current_row is not None:
                    # Si la unidad ya tenía valor (por venir en otro orden raro),
                    # priorizamos el valor que estaba más cerca (pendiente).
                    current_row[slot] = pending_value if pending_value is not None else current_row[slot]
                pending_value = None
                break

    flush()
    # Filtramos filas que no tengan cultivo (no debería pasar) o sin datos.
    return [
        r for r in results
        if r.get("cultivo") and any(r.get(k) is not None for k in ("area_sembrada_mha", "rinde_qq_ha", "produccion_mtn"))
    ]


def _find_panel_text(soup: BeautifulSoup) -> str:
    """Localiza el contenedor del panel 'Estimaciones de producción' y
    devuelve su texto con '|' como separador (para tokenizar)."""
    marker = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3", "h4", "strong", "b")
        and "Estimaciones" in tag.get_text()
    )
    if marker is None:
        return ""
    # Subimos hasta un contenedor con suficiente texto (típicamente el panel
    # entero queda en un <div> a 2-3 niveles arriba del h4).
    container = marker.find_parent()
    while container and len(container.get_text(strip=True)) < 200:
        new_container = container.find_parent()
        if new_container is None:
            break
        container = new_container
    return container.get_text("|", strip=True) if container else ""


def scrape_gea_panel(db: Session) -> dict[str, Any]:
    """Trae el panel de estimaciones GEA y upsertea las filas. Idempotente —
    si la BCR ajusta un número, se actualiza la fila correspondiente."""
    started_at = datetime.utcnow()

    try:
        response = requests.get(_PANEL_URL, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "fetch",
            "detail": str(exc),
            "started_at": started_at.isoformat(),
        }

    soup = BeautifulSoup(response.text, "html.parser")
    panel_text = _find_panel_text(soup)
    if not panel_text:
        return {
            "status": "error",
            "stage": "locate_panel",
            "detail": "No se encontró el panel 'Estimaciones de producción'",
            "started_at": started_at.isoformat(),
        }

    rows = _parse_panel_text(panel_text)
    if not rows:
        return {
            "status": "error",
            "stage": "parse_panel",
            "detail": "Panel encontrado pero sin filas parseables",
            "panel_text_preview": panel_text[:400],
            "started_at": started_at.isoformat(),
        }

    upserted = 0
    for row in rows:
        existing = (
            db.query(EstimacionGea)
            .filter(
                EstimacionGea.cultivo == row["cultivo"],
                EstimacionGea.campania == row["campania"],
            )
            .first()
        )
        if existing is None:
            db.add(EstimacionGea(
                cultivo=row["cultivo"],
                campania=row["campania"],
                area_sembrada_mha=row["area_sembrada_mha"],
                rinde_qq_ha=row["rinde_qq_ha"],
                produccion_mtn=row["produccion_mtn"],
                scraped_at=datetime.utcnow(),
            ))
        else:
            existing.area_sembrada_mha = row["area_sembrada_mha"]
            existing.rinde_qq_ha = row["rinde_qq_ha"]
            existing.produccion_mtn = row["produccion_mtn"]
            existing.scraped_at = datetime.utcnow()
        upserted += 1

    db.commit()

    return {
        "status": "ok",
        "upserted": upserted,
        "rows": rows,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Informes GEA (estimaciones nacionales mensuales).
# ---------------------------------------------------------------------------
_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_INFORME_HREF_RE = re.compile(
    r"/estimaciones-nacionales-de-produccion/estimaciones/[^/?#]+"
)


def _parse_spanish_date(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text, flags=re.IGNORECASE)
    if not m:
        return None, None
    day, month_name, year = m.groups()
    month = _SPANISH_MONTHS.get(month_name.lower())
    if not month:
        return None, None
    return (
        f"{year}-{month:02d}-{int(day):02d}",
        f"{day} de {month_name.capitalize()} de {year}",
    )


def _parse_informes_listing(html: str) -> list[dict[str, Any]]:
    """Parsea /estimaciones-anteriores devolviendo dicts {slug, titulo,
    fecha, url}. Deduplica por slug."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for link in soup.find_all("a", href=_INFORME_HREF_RE):
        href = link.get("href", "")
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if not slug or slug in seen_slugs:
            continue
        titulo = link.get_text(" ", strip=True)
        if not titulo:
            continue

        container = link.find_parent(["article", "div", "li", "section"]) or link
        container_text = container.get_text(" ", strip=True)
        fecha_iso, fecha_legible = _parse_spanish_date(container_text)
        if not fecha_iso:
            # Algunos listados muestran fecha como "MM/YYYY"; fallback torpe pero útil.
            m_short = re.search(r"(\d{1,2})/(\d{4})", container_text)
            if m_short:
                fecha_iso = f"{m_short.group(2)}-{int(m_short.group(1)):02d}-01"
                fecha_legible = f"{m_short.group(1)}/{m_short.group(2)}"

        items.append({
            "slug": slug,
            "titulo": titulo,
            "fecha": fecha_iso or "1900-01-01",
            "fecha_legible": fecha_legible,
            "url": urljoin(_BASE + "/", href),
        })
        seen_slugs.add(slug)

    return items


def _fetch_informe_body(url: str) -> tuple[str, str | None]:
    """Baja el HTML de un informe y devuelve (body_limpio, autor_si_aparece)."""
    response = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"(content|node|article)", re.IGNORECASE))
        or soup.body
    )
    if article is None:
        return "", None

    for tag in article.find_all(["nav", "script", "style", "aside", "header", "footer", "form"]):
        tag.decompose()

    text = article.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if "Descargar" in text:
        text = text.split("Descargar", 1)[1].lstrip()

    # Detectar autor: muchas notas arrancan con "Por Cristián Russo" o similar.
    autor: str | None = None
    m_autor = re.search(r"(?:^|\n)Por\s+([A-Z][a-záéíóúñ]+(?:\s+[A-Z][a-záéíóúñ]+)*)", text)
    if m_autor:
        autor = m_autor.group(1).strip()

    return text.strip(), autor


def _format_informe_txt(item: dict[str, Any], body: str, autor: str | None) -> str:
    autor_line = f"Autor: {autor}\n" if autor else ""
    return (
        f"Fecha: {item.get('fecha_legible') or item.get('fecha') or 's/d'} "
        f"({item.get('fecha') or 's/d'})\n"
        f"Fuente: BCR GEA — Estimación Nacional de Producción\n"
        f"Título: {item['titulo']}\n"
        f"{autor_line}"
        f"URL original: {item['url']}\n"
        f"Slug interno: {item['slug']}\n"
        f"\n"
        f"{body}\n"
    )


def scrape_gea_informes(
    db: Session,
    max_pages: int = _DEFAULT_INFORMES_MAX_PAGES,
    max_upload_per_run: int = _DEFAULT_INFORMES_MAX_UPLOAD,
) -> dict[str, Any]:
    """Baja el listado de informes GEA y sube los nuevos al vector store."""
    started_at = datetime.utcnow()

    if not BOT_OPENAI_API_KEY:
        return {"status": "error", "stage": "config", "detail": "OPENAI_API_KEY no configurada"}

    candidates: list[dict[str, Any]] = []
    for page in range(max_pages):
        url = _INFORMES_URL if page == 0 else f"{_INFORMES_URL}?page={page}"
        try:
            response = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            return {
                "status": "error",
                "stage": "fetch_listing",
                "page": page,
                "detail": str(exc),
            }
        items = _parse_informes_listing(response.text)
        if not items:
            break
        candidates.extend(items)
        time.sleep(_POLITE_DELAY_S)

    already = {
        r.slug
        for r in db.query(IngestedGeaReport.slug)
        .filter(IngestedGeaReport.slug.in_([c["slug"] for c in candidates]))
        .all()
    }
    new_items = [c for c in candidates if c["slug"] not in already]

    if not new_items:
        return {
            "status": "ok",
            "total_in_listing": len(candidates),
            "new_found": 0,
            "uploaded": [],
            "failed": [],
            "started_at": started_at.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
        }

    client = OpenAI(api_key=BOT_OPENAI_API_KEY)
    vs_id = ensure_vector_store_id(db, "gea", client)

    # Ordenar más viejo a más nuevo así el vector store mantiene cronología.
    to_upload = sorted(new_items, key=lambda x: x.get("fecha") or "")[:max_upload_per_run]

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in to_upload:
        try:
            body, autor = _fetch_informe_body(item["url"])
            time.sleep(_POLITE_DELAY_S)
            if not body:
                failed.append({"slug": item["slug"], "error": "empty_body"})
                continue
            content = _format_informe_txt(item, body, autor)
            filename = f"{item['fecha']}_informe_gea_{item['slug']}.txt"
            file_id = upload_text_file(client, vs_id, filename, content)
            db.add(IngestedGeaReport(
                slug=item["slug"],
                fecha=item["fecha"],
                fecha_legible=item["fecha_legible"],
                titulo=item["titulo"],
                autor=autor,
                url=item["url"],
                openai_file_id=file_id,
                ingested_at=datetime.utcnow(),
            ))
            uploaded.append({
                "slug": item["slug"],
                "titulo": item["titulo"][:80],
                "autor": autor,
                "openai_file_id": file_id,
            })
        except Exception as exc:  # noqa: BLE001
            failed.append({"slug": item["slug"], "error": f"{type(exc).__name__}: {exc}"})

    db.commit()

    return {
        "status": "ok" if not failed else "partial",
        "vector_store_id": vs_id,
        "total_in_listing": len(candidates),
        "new_found": len(new_items),
        "uploaded": uploaded,
        "failed": failed,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
    }

"""
Scraper del catálogo de cursos de BCR Capacita.

URL listado: https://www.capacitacion.bcr.com.ar/capacitacion/cursos-charlas
URL detalle: https://www.capacitacion.bcr.com.ar/capacitacion/cursos-charlas/{ID}

A diferencia del scraper de informativo (Drupal de bcr.com.ar), el sitio de
Capacita es un CMS custom server-rendered con clases no estables — el parser
busca patrones heurísticos en el texto y links en lugar de selectores CSS
específicos.

Datos disponibles en el listado: título, fecha inicio (DD/MM/YYYY),
descripción breve, URL detalle.
Datos disponibles en el detalle (cuando aparecen): modalidad, arancel,
duración. Son opcionales — si el parser no los encuentra, quedan None.

Idempotente: upsert por curso_id_externo. Re-runs reflejan cambios de fecha,
descripción o arancel sin duplicar filas.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from bot.db_models import CursoCapacita


_BASE = "https://www.capacitacion.bcr.com.ar"
_LISTING_URL = f"{_BASE}/capacitacion/cursos-charlas"
_HEADERS = {"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"}
_HTTP_TIMEOUT = 30
_POLITE_DELAY_S = 1.5

# Match del link al detalle de un curso: /capacitacion/cursos-charlas/NNNN
_CURSO_HREF_RE = re.compile(r"/capacitacion/cursos-charlas/(\d+)\b")

# Match de fecha DD/MM/YYYY en cualquier parte del texto.
_FECHA_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def _absolute(href: str) -> str:
    return urljoin(_BASE + "/", href)


def _http_get(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
    response.raise_for_status()
    return response.text


def _ddmmyyyy_to_iso(text: str) -> tuple[str | None, str | None]:
    """'05/06/2026' → ('2026-06-05', '05/06/2026'). None si no parsea."""
    m = _FECHA_RE.search(text or "")
    if not m:
        return None, None
    dd, mm, yyyy = m.groups()
    try:
        # Validamos que sea fecha real (no 30/02 etc).
        d = datetime(int(yyyy), int(mm), int(dd))
    except ValueError:
        return None, None
    return d.date().isoformat(), f"{dd}/{mm}/{yyyy}"


def _parse_listing(html: str) -> list[dict[str, Any]]:
    """Devuelve dicts {curso_id_externo, titulo, fecha_inicio,
    fecha_inicio_legible, descripcion_breve, url}.

    Estrategia robusta: para cada link a /capacitacion/cursos-charlas/NNN,
    el contenedor más cercano (article/div/li) tiene el título + la fecha +
    una descripción corta. Saca todo de ese contenedor."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    seen: set[int] = set()

    for link in soup.find_all("a", href=_CURSO_HREF_RE):
        href = link.get("href", "")
        m = _CURSO_HREF_RE.search(href)
        if not m:
            continue
        curso_id = int(m.group(1))
        if curso_id in seen:
            continue
        seen.add(curso_id)

        container = link.find_parent(["article", "div", "li", "section"]) or link
        container_text = container.get_text("\n", strip=True)

        # Título: el texto del link suele ser el título; si está vacío, primer
        # h2/h3 del container.
        titulo = link.get_text(" ", strip=True)
        if not titulo or len(titulo) < 5:
            h = container.find(["h1", "h2", "h3", "h4"])
            if h:
                titulo = h.get_text(" ", strip=True)
        if not titulo:
            continue

        fecha_iso, fecha_legible = _ddmmyyyy_to_iso(container_text)

        # Descripción breve: lo que queda del container sacando título y fecha.
        descripcion = container_text
        if titulo:
            descripcion = descripcion.replace(titulo, "", 1)
        if fecha_legible:
            descripcion = descripcion.replace(fecha_legible, "")
        descripcion = re.sub(r"\s+", " ", descripcion).strip()[:500] or None

        items.append({
            "curso_id_externo": curso_id,
            "titulo": titulo,
            "fecha_inicio": fecha_iso,
            "fecha_inicio_legible": fecha_legible,
            "descripcion_breve": descripcion,
            "url": _absolute(href),
        })

    return items


def _parse_detail(html: str) -> dict[str, Any]:
    """Extrae lo que se pueda del detalle: descripción completa, modalidad,
    arancel, duración. Todo opcional — None si no aparece."""
    soup = BeautifulSoup(html, "html.parser")

    # Cuerpo del artículo o main.
    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"(content|node|article|curso)", re.IGNORECASE))
        or soup.body
    )
    if article is None:
        return {}

    for tag in article.find_all(["nav", "script", "style", "header", "footer"]):
        tag.decompose()

    text = article.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Heurísticas: buscamos labels conocidos (case-insensitive).
    def _find_after(label_pattern: str, max_chars: int = 300) -> str | None:
        m = re.search(
            label_pattern + r"[:\-—]?\s*(.+?)(?:\n\n|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return None
        v = m.group(1).strip()
        # Cortamos en el primer label siguiente para no pisar campos.
        v = re.split(r"\n(?=[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,15}:)", v, maxsplit=1)[0]
        v = re.sub(r"\s+", " ", v).strip()
        return v[:max_chars] or None

    modalidad = _find_after(r"\bModalidad\b")
    arancel = _find_after(r"\b(?:Arancel|Costo|Precio|Valor|Inversi[oó]n)\b")
    duracion = _find_after(r"\b(?:Duraci[oó]n|Carga\s+hor[ao]ria|Horas?)\b", max_chars=120)

    # Descripción larga: tomamos los primeros ~1500 chars de texto significativo.
    descripcion_full = text[:1500] if text else None

    return {
        "modalidad": modalidad,
        "arancel": arancel,
        "duracion": duracion,
        "descripcion_full": descripcion_full,
    }


def scrape_capacita(
    db: Session,
    fetch_details: bool = True,
    max_detail_fetches: int = 60,
) -> dict[str, Any]:
    """Recorre el catálogo de cursos y actualiza la tabla cursos_capacita."""
    started_at = datetime.utcnow()

    try:
        html = _http_get(_LISTING_URL)
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "fetch_listing",
            "detail": str(exc),
            "started_at": started_at.isoformat(),
        }

    listing = _parse_listing(html)
    if not listing:
        return {
            "status": "error",
            "stage": "parse_listing",
            "detail": "No se encontraron cursos en el listado",
            "started_at": started_at.isoformat(),
        }

    upserted: list[dict[str, Any]] = []
    detail_failed: list[dict[str, Any]] = []

    # Priorizamos fetch de detalles para cursos con fecha (los actionables);
    # los históricos sin fecha quedan con info de listado solamente.
    # Esto nos da info completa de los cursos vigentes sin disparar 290
    # requests en una sola corrida.
    listing_sorted = sorted(
        listing,
        key=lambda x: (x["fecha_inicio"] is None, x["fecha_inicio"] or ""),
    )

    for i, item in enumerate(listing_sorted):
        detail: dict[str, Any] = {}
        # Solo cursos con fecha se fetchea detalle, y siempre dentro del cap.
        should_fetch = (
            fetch_details
            and item["fecha_inicio"] is not None
            and i < max_detail_fetches
        )
        if should_fetch:
            try:
                d_html = _http_get(item["url"])
                detail = _parse_detail(d_html)
                time.sleep(_POLITE_DELAY_S)
            except requests.RequestException as exc:
                detail_failed.append({
                    "curso_id_externo": item["curso_id_externo"],
                    "error": str(exc),
                })

        # Combinamos: descripción del listado o la del detalle (más larga).
        desc = detail.get("descripcion_full") or item.get("descripcion_breve")

        existing = (
            db.query(CursoCapacita)
            .filter(CursoCapacita.curso_id_externo == item["curso_id_externo"])
            .first()
        )
        fields = {
            "titulo": item["titulo"],
            "fecha_inicio": item["fecha_inicio"],
            "fecha_inicio_legible": item["fecha_inicio_legible"],
            "descripcion": desc,
            "modalidad": detail.get("modalidad"),
            "arancel": detail.get("arancel"),
            "duracion": detail.get("duracion"),
            "url": item["url"],
            "scraped_at": datetime.utcnow(),
        }
        if existing is None:
            db.add(CursoCapacita(curso_id_externo=item["curso_id_externo"], **fields))
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
        upserted.append({
            "curso_id_externo": item["curso_id_externo"],
            "titulo": item["titulo"][:60],
            "fecha_inicio": item["fecha_inicio"],
        })

    db.commit()

    return {
        "status": "ok" if not detail_failed else "partial",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "upserted": len(upserted),
        "upserted_sample": upserted[:5],
        "detail_failed": detail_failed,
    }

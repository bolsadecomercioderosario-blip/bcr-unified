"""
Scraper del BCR Startup Network (https://www.innova.bcr.com.ar/startupnetwork).

La página muestra ~150+ startups en cards (grid), todas con info inline:
nombre, sector/vertical (Agrifoodtech, Biotech, Fintech, etc.), descripción
breve, link al sitio web externo, y posiblemente edición del programa
(BCR SN 1.0 — 6.0).

A diferencia de los otros scrapers, NO hay páginas de detalle propias —
toda la info está en el grid del listado. La startup misma tiene su web
externa pero no la scrapeamos (sería abrir un volumen impracticable de
sitios distintos).

Idempotente: upsert por (nombre, edicion).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from bot.db_models import StartupInnova


_BASE = "https://www.innova.bcr.com.ar"
_LISTING_URL = f"{_BASE}/startupnetwork"
_HEADERS = {"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"}
_HTTP_TIMEOUT = 30

# Sectores canónicos que aparecen en el filtro del sitio. Sirven para detectar
# cuál es el sector de cada startup (la palabra aparece en algún lugar de la card).
_KNOWN_SECTORS = (
    "Agrifoodtech",
    "Animaltech",
    "Biotech",
    "Climatech",
    "Fintech",
    "Industria 4.0",
)

# Ediciones del programa que aparecen en el filtro (BCR SN 1.0 — 6.0).
_EDITION_RE = re.compile(r"BCR\s*SN\s*\d+(?:\.\d+)?", re.IGNORECASE)


def _http_get(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
    response.raise_for_status()
    return response.text


def _detect_sector(text: str) -> str | None:
    """Busca cuál de los sectores canónicos aparece en el texto de la card."""
    lower = text.lower()
    for s in _KNOWN_SECTORS:
        if s.lower() in lower:
            return s
    return None


def _detect_edition(text: str) -> str | None:
    m = _EDITION_RE.search(text)
    return m.group(0).replace("  ", " ").strip() if m else None


def _parse_startups(html: str) -> list[dict[str, Any]]:
    """Cada card de startup tiene el nombre en <h5 class="card-title"> y el
    cuerpo en <div class="card-body">. Iteramos por el título de cada card
    y subimos al card-body para extraer el resto."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()

    # Buscamos por los títulos de las cards — esa es la marca estable. El
    # contenedor de la card sube uno o dos niveles desde el título.
    title_tags = soup.find_all(
        ["h5", "h4", "h3", "h2"],
        class_=re.compile(r"card-title", re.IGNORECASE),
    )

    for name_tag in title_tags:
        nombre = name_tag.get_text(" ", strip=True)
        if not nombre or len(nombre) < 2 or len(nombre) > 80:
            continue
        # Skip headers obvios del sitio (por las dudas).
        if nombre.lower() in {
            "startup network", "bcr startup network", "nuestro ecosistema",
            "innova", "novedades", "contacto",
        }:
            continue

        # Card body: el padre del título suele ser <div class="card-body">.
        card = name_tag.find_parent("div", class_=re.compile(r"card", re.IGNORECASE))
        if card is None:
            card = name_tag.parent

        card_text = card.get_text(" ", strip=True)
        sector = _detect_sector(card_text)
        edicion = _detect_edition(card_text)

        # Website externo: primer link http(s) que no sea de innova.bcr.com.ar
        website = None
        for a in card.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith(("http://", "https://")):
                continue
            if "innova.bcr.com.ar" in href or "bcr.com.ar" in href:
                continue
            website = href
            break

        # Descripción: texto de la card sacando nombre, sector y "SITIO WEB"
        desc = card_text
        for tok in (nombre, sector or "", edicion or "", "SITIO WEB", "Sitio Web"):
            if tok:
                desc = desc.replace(tok, "")
        desc = re.sub(r"\s+", " ", desc).strip()[:400] or None

        key = (nombre.lower(), edicion)
        if key in seen:
            continue
        seen.add(key)

        items.append({
            "nombre": nombre,
            "sector": sector,
            "edicion": edicion,
            "descripcion": desc,
            "website_url": website,
        })

    return items


def scrape_startups_innova(db: Session) -> dict[str, Any]:
    """Recorre el listado y upsertea startups por (nombre, edicion)."""
    started_at = datetime.utcnow()

    try:
        html = _http_get(_LISTING_URL)
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "fetch",
            "detail": str(exc),
            "started_at": started_at.isoformat(),
        }

    items = _parse_startups(html)
    if not items:
        return {
            "status": "error",
            "stage": "parse",
            "detail": "No se encontraron startups en el listado",
            "started_at": started_at.isoformat(),
        }

    upserted = 0
    sectors_seen: dict[str, int] = {}

    for item in items:
        existing = (
            db.query(StartupInnova)
            .filter(
                StartupInnova.nombre == item["nombre"],
                # Comparación NULL-safe: si edicion es None en ambos lados, matchea.
                (StartupInnova.edicion == item["edicion"])
                if item["edicion"] is not None
                else StartupInnova.edicion.is_(None),
            )
            .first()
        )
        if existing is None:
            db.add(StartupInnova(
                nombre=item["nombre"],
                sector=item["sector"],
                edicion=item["edicion"],
                descripcion=item["descripcion"],
                website_url=item["website_url"],
                scraped_at=datetime.utcnow(),
            ))
        else:
            existing.sector = item["sector"]
            existing.descripcion = item["descripcion"]
            existing.website_url = item["website_url"]
            existing.scraped_at = datetime.utcnow()
        upserted += 1
        if item["sector"]:
            sectors_seen[item["sector"]] = sectors_seen.get(item["sector"], 0) + 1

    db.commit()

    return {
        "status": "ok",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "upserted": upserted,
        "total_in_page": len(items),
        "sectors_seen": sectors_seen,
    }

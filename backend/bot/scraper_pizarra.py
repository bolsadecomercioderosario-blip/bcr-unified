"""
Scraper de precios pizarra del Mercado Físico de Rosario.

Estructura de la tabla del sitio (verificada al desarrollar 3.1):
  Header: [Fecha Negociación] [Trading date] [DD/MM/YYYY] x 5 días
  Data:   [Producto ES]       [Producto EN]  [$ NNN.NNN,NN o "S/C"] x 5

Cada corrida:
- Baja la página de cotizaciones
- Parsea las 5 fechas del header y los precios de cada producto
- Hace upsert sobre (producto_normalizado, fecha YYYY-MM-DD) en
  precios_pizarra. Idempotente: si el sitio ajusta un precio retroactivo,
  la fila se actualiza.

El cron del chunk 3.1 lo dispara diariamente; también hay un endpoint
admin que lo corre on-demand para debuggear.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from bot.db_models import PrecioPizarra


PRECIOS_URL = (
    "https://www.bcr.com.ar/es/mercados/mercado-de-granos/cotizaciones/"
    "cotizaciones-locales-0"
)

# Las primeras 2 columnas de la tabla no son fechas — son las etiquetas
# "Fecha Negociación" y "Trading date".
_NON_DATE_HEADER_COLUMNS = 2

# Misma lógica para data rows: cols[0] = producto ES, cols[1] = producto EN,
# cols[2:] = precios uno por fecha.
_NON_PRICE_DATA_COLUMNS = 2

# Texto que el sitio usa cuando no hay cotización para una fecha.
_NO_QUOTE_MARKERS = {"s/c", "s/d", "sin cotizacion", "sin cotización", "-", "—", ""}


def _normalize_product(name: str) -> str:
    """'Soja' → 'soja'; 'Maíz' → 'maiz'. Sin acentos, lowercase, sin espacios."""
    decomposed = unicodedata.normalize("NFKD", name)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", no_accents).strip().lower()


def _parse_ars_price(text: str) -> float | None:
    """Convierte '$ 460.000,00' a 460000.0. Devuelve None si la celda dice
    'S/C' o similar (sin cotización).

    Formato argentino: punto separador de miles, coma decimal.
    """
    clean = text.strip().lower()
    if clean in _NO_QUOTE_MARKERS:
        return None
    # Quita $, espacios, y caracteres no numéricos excepto . y ,
    clean = re.sub(r"[^\d.,-]", "", clean)
    if not clean:
        return None
    # Quita separadores de miles ('.') y reemplaza coma decimal por punto.
    clean = clean.replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None


def _parse_iso_date(text: str) -> str | None:
    """'20/05/2026' → '2026-05-20'. None si no parsea."""
    text = text.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _pick_price_table(soup: BeautifulSoup):
    """La página tiene varias <table>; agarramos la que más se parece a la
    de precios: una con un header que tenga al menos 3 columnas con fechas
    DD/MM/YYYY. Más robusto que confiar en el orden o en una clase CSS que
    no sabemos si tiene."""
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        cells = first_row.find_all(["th", "td"])
        date_count = sum(1 for c in cells if _parse_iso_date(c.get_text(strip=True)))
        if date_count >= 3:
            return table
    return None


def scrape_precios_pizarra(db: Session) -> dict[str, Any]:
    """Corre el scraper una vez. Devuelve un dict con métricas para loguear/
    monitorear desde el admin endpoint.

    Idempotente: hace upsert sobre (producto, fecha). Si el sitio cambia un
    precio retroactivamente, la fila se actualiza; nunca se duplica.
    """
    started_at = datetime.utcnow()
    try:
        response = requests.get(
            PRECIOS_URL,
            headers={"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "fetch",
            "detail": str(exc),
            "started_at": started_at.isoformat(),
        }

    soup = BeautifulSoup(response.text, "html.parser")
    table = _pick_price_table(soup)
    if table is None:
        return {
            "status": "error",
            "stage": "parse_table",
            "detail": "No se encontró tabla de precios con fechas en el header",
            "started_at": started_at.isoformat(),
        }

    rows = table.find_all("tr")
    if not rows:
        return {
            "status": "error",
            "stage": "parse_rows",
            "detail": "Tabla vacía",
            "started_at": started_at.isoformat(),
        }

    # Header: extraemos fechas.
    header_cells = rows[0].find_all(["th", "td"])
    dates_iso: list[str | None] = [
        _parse_iso_date(c.get_text(strip=True))
        for c in header_cells[_NON_DATE_HEADER_COLUMNS:]
    ]

    upserted = 0
    skipped_no_quote = 0
    skipped_unparseable = 0
    products_seen: set[str] = set()

    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) <= _NON_PRICE_DATA_COLUMNS:
            continue

        producto = _normalize_product(cells[0].get_text(strip=True))
        if not producto:
            continue
        products_seen.add(producto)

        price_cells = cells[_NON_PRICE_DATA_COLUMNS:]
        for date_iso, cell in zip(dates_iso, price_cells):
            if not date_iso:
                continue
            raw = cell.get_text(strip=True)
            price = _parse_ars_price(raw)
            if price is None:
                if raw.lower() in _NO_QUOTE_MARKERS:
                    skipped_no_quote += 1
                else:
                    skipped_unparseable += 1
                continue

            existing = (
                db.query(PrecioPizarra)
                .filter(
                    PrecioPizarra.producto == producto,
                    PrecioPizarra.fecha == date_iso,
                )
                .first()
            )
            if existing is None:
                db.add(PrecioPizarra(
                    producto=producto,
                    fecha=date_iso,
                    precio_ars_tn=price,
                    scraped_at=datetime.utcnow(),
                ))
            else:
                existing.precio_ars_tn = price
                existing.scraped_at = datetime.utcnow()
            upserted += 1

    db.commit()

    return {
        "status": "ok",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "upserted": upserted,
        "skipped_no_quote": skipped_no_quote,
        "skipped_unparseable": skipped_unparseable,
        "dates_in_header": [d for d in dates_iso if d],
        "products_seen": sorted(products_seen),
    }

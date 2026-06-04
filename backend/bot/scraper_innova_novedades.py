"""
Scraper de las Novedades de BCR Innova (https://www.innova.bcr.com.ar/novedades).

innova.bcr.com.ar es Drupal — mismo CMS que el bcr.com.ar principal — así
que el patrón es muy similar al de informativo: listado + links a detalle
por node_id (URL /node/NNNN), cada novedad tiene fecha DD/MM/YYYY visible
en la card del listado.

Idempotente: tabla ingested_novedades_innova trackea qué node_ids ya
subimos. Cada corrida sube los nuevos como TXT al vector store
'BCR Innova Novedades' (auto-bootstrap igual que comentarios/informativo).
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

from bot.db_models import IngestedNovedadInnova
from bot.openai_vector_stores import ensure_vector_store_id, upload_text_file


_BASE = "https://www.innova.bcr.com.ar"
_LISTING_URL = f"{_BASE}/novedades"
_HEADERS = {"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"}
_HTTP_TIMEOUT = 30
_POLITE_DELAY_S = 1.5

# Cap por corrida — la sección /novedades no recibe novedades a cientos por
# semana; en el primer run podemos subir un backfill chico (15 entradas).
_DEFAULT_MAX_UPLOAD = 15

# Drupal expone las novedades por /node/NNNN. También aceptamos /novedades/...
# por si el sitio agrega slugs amigables en el futuro.
_DETAIL_LINK_RE = re.compile(r"/(?:node|novedades)/(\d+)\b")

_FECHA_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def _absolute(href: str) -> str:
    return urljoin(_BASE + "/", href)


def _http_get(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
    response.raise_for_status()
    return response.text


def _parse_ddmmyyyy(text: str) -> tuple[str | None, str | None]:
    m = _FECHA_RE.search(text or "")
    if not m:
        return None, None
    dd, mm, yyyy = m.groups()
    try:
        d = datetime(int(yyyy), int(mm), int(dd))
    except ValueError:
        return None, None
    return d.date().isoformat(), f"{dd}/{mm}/{yyyy}"


def _parse_listing(html: str) -> list[dict[str, Any]]:
    """Devuelve dicts {node_id, titulo, fecha, fecha_legible,
    descripcion_breve, url} para cada novedad encontrada en la página."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    seen: set[int] = set()

    for link in soup.find_all("a", href=_DETAIL_LINK_RE):
        href = link.get("href", "")
        m = _DETAIL_LINK_RE.search(href)
        if not m:
            continue
        node_id = int(m.group(1))
        if node_id in seen:
            continue

        # Subimos por los parents hasta encontrar uno que tenga la fecha de
        # la novedad (las cards de Drupal en este sitio tienen estructura
        # anidada: el link está en <h2><div>, y la fecha vive en el
        # <div class="card-news"> dos niveles arriba). Sin esto perdemos
        # fechas porque find_parent('div') agarra el wrapper más chico.
        container = None
        cursor = link
        for _ in range(6):
            cursor = cursor.parent if cursor else None
            if cursor is None:
                break
            if _FECHA_RE.search(cursor.get_text(" ", strip=True)):
                container = cursor
                break
        if container is None:
            container = link.find_parent(["article", "div", "li", "section"]) or link

        # Título: texto del link; si vacío o muy corto, heading del container.
        titulo = link.get_text(" ", strip=True)
        if not titulo or len(titulo) < 5:
            h = container.find(["h1", "h2", "h3", "h4"])
            if h:
                titulo = h.get_text(" ", strip=True)
        if not titulo:
            continue

        container_text = container.get_text("\n", strip=True)
        fecha_iso, fecha_legible = _parse_ddmmyyyy(container_text)

        # Descripción breve: limpiamos título + fecha del texto del container.
        desc = container_text
        if titulo:
            desc = desc.replace(titulo, "", 1)
        if fecha_legible:
            desc = desc.replace(fecha_legible, "")
        desc = re.sub(r"\s+", " ", desc).strip()[:400] or None

        items.append({
            "node_id": node_id,
            "titulo": titulo,
            "fecha": fecha_iso,
            "fecha_legible": fecha_legible,
            "descripcion_breve": desc,
            "url": _absolute(href),
        })
        seen.add(node_id)

    return items


def _fetch_novedad_body(url: str) -> str:
    """Baja el detalle y devuelve texto plano limpio.

    En este sitio el <article> wrappea solo la imagen (sin texto) y el
    contenido vive en <main>. Elegimos el contenedor con más texto entre
    los candidatos en lugar de tomar el primero a ciegas. Para limpiar
    chrome de navegación remanente (el sitio mete el menú dentro del
    <main>), cortamos todo lo anterior al botón "Volver".
    """
    html = _http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    candidates = [
        soup.find("main"),
        soup.find("article"),
        soup.find("div", class_=re.compile(r"(content|node|novedad)", re.IGNORECASE)),
        soup.body,
    ]
    candidates = [c for c in candidates if c is not None]
    if not candidates:
        return ""

    article = max(candidates, key=lambda el: len(el.get_text(strip=True)))

    for tag in article.find_all(["nav", "script", "style", "aside", "header", "footer", "form"]):
        tag.decompose()

    text = article.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Cortar todo antes de 'Volver' (botón de regreso al listado). Lo que
    # viene después de esa palabra es el cuerpo real de la novedad.
    if "Volver" in text:
        text = text.split("Volver", 1)[1].lstrip()

    return text.strip()


def _format_txt(item: dict[str, Any], body: str) -> str:
    return (
        f"Fecha: {item.get('fecha_legible') or item.get('fecha') or 's/d'} "
        f"({item.get('fecha') or 's/d'})\n"
        f"Fuente: BCR Innova — Novedades\n"
        f"Título: {item['titulo']}\n"
        f"URL original: {item['url']}\n"
        f"Node ID: {item['node_id']}\n"
        f"\n"
        f"{body}\n"
    )


def scrape_innova_novedades(
    db: Session,
    max_upload_per_run: int = _DEFAULT_MAX_UPLOAD,
) -> dict[str, Any]:
    """Recorre el listado de novedades, sube las nuevas al vector store."""
    started_at = datetime.utcnow()

    if not BOT_OPENAI_API_KEY:
        return {"status": "error", "stage": "config", "detail": "OPENAI_API_KEY no configurada"}

    try:
        html = _http_get(_LISTING_URL)
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "fetch_listing",
            "detail": str(exc),
            "started_at": started_at.isoformat(),
        }

    candidates = _parse_listing(html)
    if not candidates:
        return {
            "status": "error",
            "stage": "parse_listing",
            "detail": "Listado de novedades vacío",
            "started_at": started_at.isoformat(),
        }

    already = {
        r.node_id
        for r in db.query(IngestedNovedadInnova.node_id)
        .filter(IngestedNovedadInnova.node_id.in_([c["node_id"] for c in candidates]))
        .all()
    }
    new_items = [c for c in candidates if c["node_id"] not in already]

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
    vs_id = ensure_vector_store_id(db, "novedades_innova", client)

    # Ordenamos por fecha ascendente para que el vector store mantenga orden
    # cronológico cuando hagamos backfill chico.
    to_upload = sorted(new_items, key=lambda x: x.get("fecha") or "")[:max_upload_per_run]

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in to_upload:
        try:
            body = _fetch_novedad_body(item["url"])
            time.sleep(_POLITE_DELAY_S)
            if not body:
                failed.append({"node_id": item["node_id"], "error": "empty_body"})
                continue
            content = _format_txt(item, body)
            fecha = item.get("fecha") or "sd"
            filename = f"{fecha}_novedad_innova_{item['node_id']}.txt"
            file_id = upload_text_file(client, vs_id, filename, content)

            db.add(IngestedNovedadInnova(
                node_id=item["node_id"],
                titulo=item["titulo"],
                fecha=item.get("fecha"),
                fecha_legible=item.get("fecha_legible"),
                descripcion_breve=item.get("descripcion_breve"),
                url=item["url"],
                openai_file_id=file_id,
                ingested_at=datetime.utcnow(),
            ))
            uploaded.append({
                "node_id": item["node_id"],
                "titulo": item["titulo"][:80],
                "fecha": item.get("fecha"),
                "openai_file_id": file_id,
            })
        except Exception as exc:  # noqa: BLE001
            failed.append({"node_id": item["node_id"], "error": f"{type(exc).__name__}: {exc}"})

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

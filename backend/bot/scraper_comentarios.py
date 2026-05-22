"""
Scraper de los Comentarios Diarios del Mercado de la BCR.

URL listado:  /es/mercados/mercado-de-granos/comentario-del-mercado/
              comentario-del-mercado-{local|chicago}
URL detalle: .../{listado}/comentario-NNNN

Patrón:
- Comentario IDs son enteros secuenciales descendentes
- Fecha está en el listado ("20 de Mayo de 2026"), no en el detalle
- Cuerpo es HTML, lo bajamos a texto plano y lo subimos como TXT al
  vector store de "Comentarios Diarios" (auto-creado si no existe).

Idempotente: tabla ingested_comentarios trackea qué (source, comentario_id)
ya subimos. Cada corrida del scraper sólo agarra los nuevos.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from sqlalchemy.orm import Session

from config import BOT_OPENAI_API_KEY

from bot.db_models import IngestedComentario
from bot.openai_vector_stores import ensure_vector_store_id, upload_text_file


_BASE = "https://www.bcr.com.ar"
_LISTING_URL = {
    "local": f"{_BASE}/es/mercados/mercado-de-granos/comentario-del-mercado/comentario-del-mercado-local",
    "chicago": f"{_BASE}/es/mercados/mercado-de-granos/comentario-del-mercado/comentario-del-mercado-chicago",
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"}
_HTTP_TIMEOUT = 30

# Por corrida, cuánto retroceder. 1 página alcanza para el day-to-day (la
# página 0 muestra ~10 últimos comentarios). Si nunca corrió el scraper y
# querés un mini-backfill, dispará con max_pages mayor desde el admin endpoint.
_DEFAULT_MAX_PAGES = 1

# Máximo de comentarios nuevos que subimos por corrida. Evita que un primer
# run accidentalmente suba 300 archivos a OpenAI de un saque (caro y lento).
_DEFAULT_MAX_UPLOAD_PER_RUN = 25


_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_spanish_date(text: str) -> tuple[str | None, str | None]:
    """'20 de Mayo de 2026' → ('2026-05-20', '20 de Mayo de 2026').
    Devuelve (None, None) si no parsea."""
    if not text:
        return None, None
    m = re.search(
        r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None, None
    day, month_name, year = m.groups()
    month = _SPANISH_MONTHS.get(month_name.lower())
    if not month:
        return None, None
    iso = f"{year}-{month:02d}-{int(day):02d}"
    legible = f"{day} de {month_name.capitalize()} de {year}"
    return iso, legible


def _absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return _BASE + href
    return _BASE + "/" + href


def _parse_listing_page(html: str, source: str) -> list[dict[str, Any]]:
    """Parsea un listado y devuelve dicts {source, comentario_id, fecha,
    fecha_legible, url}. Robusto a cambios menores en el markup: busca
    links que matcheen /comentario-NNNN y trepa al contenedor más cercano
    para encontrar la fecha."""
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for link in soup.find_all("a", href=re.compile(r"/comentario-\d+")):
        href = link.get("href", "")
        m = re.search(r"/comentario-(\d+)", href)
        if not m:
            continue
        comentario_id = int(m.group(1))
        if comentario_id in seen_ids:
            continue

        # Buscamos la fecha en el container más cercano (el item del listado).
        container = link.find_parent(["article", "div", "li", "section"]) or link
        container_text = container.get_text(separator=" ", strip=True)
        fecha_iso, fecha_legible = _parse_spanish_date(container_text)
        if not fecha_iso:
            continue

        items.append({
            "source": source,
            "comentario_id": comentario_id,
            "fecha": fecha_iso,
            "fecha_legible": fecha_legible,
            "url": _absolute_url(href),
        })
        seen_ids.add(comentario_id)

    return items


def _fetch_comentario_body(url: str) -> str:
    """Baja el HTML del detalle, extrae el texto del cuerpo principal.

    El sitio de BCR mete el breadcrumb (Home / Mercados / ...) y el título
    al inicio del article. Heurística: descartamos todo lo que esté antes
    del botón 'Descargar' (que separa el header del cuerpo del artículo)."""
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
        return ""

    # Sacamos chrome (nav, footer, scripts) para quedarnos con el cuerpo.
    for tag in article.find_all(["nav", "script", "style", "aside", "header", "footer", "form"]):
        tag.decompose()

    text = article.get_text(separator="\n", strip=True)
    # Compactar múltiples newlines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Cortar el breadcrumb + título: el botón 'Descargar' aparece justo
    # antes del cuerpo real del comentario. Si el texto no lo contiene
    # (caso edge), devolvemos lo que hay.
    if "Descargar" in text:
        text = text.split("Descargar", 1)[1].lstrip()

    return text.strip()


def _format_txt(item: dict[str, Any], body: str) -> str:
    """Arma el TXT que va al vector store, con metadata fielmente arriba para
    que el LLM la cite cuando responda."""
    return (
        f"Fecha: {item['fecha_legible']} ({item['fecha']})\n"
        f"Fuente: BCR Comentario Diario del Mercado Físico de Rosario "
        f"({item['source'].title()})\n"
        f"URL original: {item['url']}\n"
        f"ID interno: {item['comentario_id']}\n"
        f"\n"
        f"{body}\n"
    )


def scrape_comentarios(
    db: Session,
    source: str = "local",
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_upload_per_run: int = _DEFAULT_MAX_UPLOAD_PER_RUN,
) -> dict[str, Any]:
    """Corre el scraper para una fuente ('local' o 'chicago')."""
    started_at = datetime.utcnow()

    if source not in _LISTING_URL:
        return {"status": "error", "stage": "validate", "detail": f"source inválida: {source!r}"}

    if not BOT_OPENAI_API_KEY:
        return {"status": "error", "stage": "config", "detail": "OPENAI_API_KEY no configurada"}

    # 1. Levantamos las páginas del listado y recolectamos candidatos.
    listing_url = _LISTING_URL[source]
    candidates: list[dict[str, Any]] = []
    for page in range(max_pages):
        url = listing_url if page == 0 else f"{listing_url}?page={page}"
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
        page_items = _parse_listing_page(response.text, source)
        if not page_items:
            break
        candidates.extend(page_items)

    # 2. Filtramos los que ya teníamos.
    already = {
        r.comentario_id
        for r in db.query(IngestedComentario.comentario_id)
        .filter(IngestedComentario.source == source)
        .all()
    }
    new_items = [c for c in candidates if c["comentario_id"] not in already]

    if not new_items:
        return {
            "status": "ok",
            "source": source,
            "total_in_listing": len(candidates),
            "already_ingested": len(candidates),
            "uploaded": [],
            "failed": [],
            "started_at": started_at.isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
        }

    # 3. Vector store (auto-crea si no estaba).
    client = OpenAI(api_key=BOT_OPENAI_API_KEY)
    vs_id = ensure_vector_store_id(db, "comentarios", client)

    # 4. Subir nuevos (ordenados de más viejo a más nuevo, para que el
    # vector store mantenga orden cronológico al consultar).
    to_upload = sorted(new_items, key=lambda x: x["comentario_id"])[:max_upload_per_run]

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for item in to_upload:
        try:
            body = _fetch_comentario_body(item["url"])
            if not body:
                failed.append({"comentario_id": item["comentario_id"], "error": "empty_body"})
                continue
            content = _format_txt(item, body)
            filename = (
                f"{item['fecha']}_comentario_{source}_{item['comentario_id']}.txt"
            )
            file_id = upload_text_file(client, vs_id, filename, content)

            db.add(IngestedComentario(
                source=source,
                comentario_id=item["comentario_id"],
                fecha=item["fecha"],
                fecha_legible=item["fecha_legible"],
                url=item["url"],
                openai_file_id=file_id,
                ingested_at=datetime.utcnow(),
            ))
            uploaded.append({
                "comentario_id": item["comentario_id"],
                "fecha": item["fecha"],
                "openai_file_id": file_id,
            })
        except Exception as exc:  # noqa: BLE001 — capturamos por item para no abortar la corrida
            failed.append({
                "comentario_id": item["comentario_id"],
                "error": f"{type(exc).__name__}: {exc}",
            })

    db.commit()

    return {
        "status": "ok" if not failed else "partial",
        "source": source,
        "vector_store_id": vs_id,
        "total_in_listing": len(candidates),
        "new_found": len(new_items),
        "uploaded": uploaded,
        "failed": failed,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
    }

"""
Scraper del Informativo Semanal de la BCR.

Cubre dos casos de uso:
1. scrape_current_edition(db): cron del viernes. Trae los artículos nuevos
   de la edición vigente y los sube al vector store.
2. backfill_past_editions(db, max_editions): one-shot manual desde el admin
   endpoint. Recorre /ediciones-anteriores y ingesta hasta `max_editions`
   pasadas que no estén ya en la DB.

Patrón de las páginas de edición (verificado al desarrollar):
- <h2>AÑO XLV - Edición N° 2243 - 15 de Mayo de 2026</h2>
- Cada artículo es un <a href=".../noticias-informativo-semanal/SLUG">Título</a>
- Todos los artículos de una edición comparten su fecha.

Patrón del listado de ediciones anteriores:
- Cada edición: link "AÑO XLV - Edición N° 2242" + fecha "08 de Mayo de 2026"
- Paginación ?page=X

Tabla de tracking: ingested_informativo_articles (slug es UNIQUE).
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

from bot.db_models import IngestedInformativoArticle
from bot.openai_vector_stores import ensure_vector_store_id, upload_text_file


_BASE = "https://www.bcr.com.ar"
_CURRENT_EDITION_URL = (
    f"{_BASE}/es/mercados/investigacion-y-desarrollo/informativo-semanal"
)
_PAST_EDITIONS_URL = (
    f"{_BASE}/es/mercados/investigacion-y-desarrollo/informativo-semanal/"
    "ediciones-anteriores-del-informativo"
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (BCR Bot Scraper)"}
_HTTP_TIMEOUT = 30

# Cap del backfill — no querés que un solo POST suba miles de archivos en
# una corrida (ni por costo OpenAI ni por gentileza con el server de BCR).
_BACKFILL_DEFAULT_MAX_EDITIONS = 8
_BACKFILL_DEFAULT_MAX_ARTICLES = 40

# Pausa entre requests al sitio de BCR durante el backfill. No queremos
# parecernos a un scraper hostil.
_POLITE_DELAY_S = 1.5

# Match del link a un artículo individual del informativo.
_ARTICLE_HREF_RE = re.compile(
    r"/informativo-semanal/noticias-informativo-semanal(?:-\d+)?/[^/?#]+"
)

# Match del link a una edición pasada en /ediciones-anteriores.
_EDITION_HREF_RE = re.compile(r"/boletin-informativo-semanal/")

# Secciones canónicas del informativo. Sirven como whitelist al detectar
# en qué sección está cada artículo — si lo que aparece arriba del link
# no es una de éstas, no se asigna sección (mejor None que basura).
_KNOWN_SECCIONES = (
    "Commodities",
    "Reporte del Mercado de Granos",
    "Reporte del mercado de granos",
    "Economía",
    "Economia",
    "Oferta y Demanda proyectada",
    "Oferta y Demanda Proyectada",
)


_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_spanish_date(text: str) -> tuple[str | None, str | None]:
    """'15 de Mayo de 2026' → ('2026-05-15', '15 de Mayo de 2026')."""
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
    return (
        f"{year}-{month:02d}-{int(day):02d}",
        f"{day} de {month_name.capitalize()} de {year}",
    )


def _parse_edition_heading(text: str) -> dict[str, Any]:
    """'AÑO XLV - Edición N° 2243 - 15 de Mayo de 2026' →
    {'anio_roman': 'XLV', 'numero': 2243, 'fecha': '2026-05-15',
     'fecha_legible': '15 de Mayo de 2026'}. Campos faltantes = None.
    """
    out: dict[str, Any] = {
        "anio_roman": None,
        "numero": None,
        "fecha": None,
        "fecha_legible": None,
    }
    if not text:
        return out

    m_anio = re.search(r"A[ÑN]O\s+([IVXLCDM]+)", text, flags=re.IGNORECASE)
    if m_anio:
        out["anio_roman"] = m_anio.group(1).upper()

    m_num = re.search(r"Edici[oó]n\s+N[°º]?\s*(\d+)", text, flags=re.IGNORECASE)
    if m_num:
        out["numero"] = int(m_num.group(1))

    fecha_iso, fecha_legible = _parse_spanish_date(text)
    out["fecha"] = fecha_iso
    out["fecha_legible"] = fecha_legible

    return out


def _absolute(href: str) -> str:
    return urljoin(_BASE + "/", href)


def _http_get(url: str) -> str:
    response = requests.get(url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
    response.raise_for_status()
    return response.text


def _parse_edition_page(html: str) -> dict[str, Any]:
    """Parsea una página de edición (vigente o pasada). Devuelve metadata
    de la edición + lista de artículos.

    Heurística para 'sección': busca el contenedor del link y trepa hasta
    encontrar un heading (h2/h3/h4) que matchee una sección conocida.
    Si no aparece, sección = None (no es crítico para el LLM).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Heading principal de la edición.
    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3")
        and "Edici" in tag.get_text()
    )
    if heading is None:
        # A veces el heading viene como texto suelto antes de los artículos;
        # buscamos cualquier texto que matchee el patrón.
        body_text = soup.get_text(" ", strip=True)
        edition_meta = _parse_edition_heading(body_text)
    else:
        edition_meta = _parse_edition_heading(heading.get_text(" ", strip=True))

    # Artículos.
    articles: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    for link in soup.find_all("a", href=_ARTICLE_HREF_RE):
        href = link.get("href", "")
        # Slug = última parte del path.
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        if not slug or slug in seen_slugs:
            continue
        titulo = link.get_text(" ", strip=True)
        if not titulo:
            continue

        # Sección: nos quedamos con la sección canónica más cercana
        # buscando hacia atrás en el flujo del documento. Si no aparece
        # una de la whitelist, sección = None (mejor que basura).
        seccion = None
        prev_text = ""
        cursor = link
        for _ in range(20):
            cursor = cursor.find_previous(string=True) if cursor else None
            if cursor is None:
                break
            txt = str(cursor).strip()
            if not txt:
                continue
            for known in _KNOWN_SECCIONES:
                if known.lower() == txt.lower() or txt.lower().endswith(known.lower()):
                    seccion = known
                    break
            if seccion:
                break
            prev_text = txt
            if len(prev_text) > 200:
                break

        articles.append({
            "slug": slug,
            "titulo": titulo,
            "seccion": seccion,
            "url": _absolute(href),
        })
        seen_slugs.add(slug)

    return {
        **edition_meta,
        "articles": articles,
    }


def _fetch_article_body(url: str) -> str:
    """Baja el HTML de un artículo y extrae el cuerpo. Mismo patrón que
    el scraper de comentarios: cortar el chrome (breadcrumb + título) si
    aparece 'Descargar' (botón de descarga PDF)."""
    html = _http_get(url)
    soup = BeautifulSoup(html, "html.parser")

    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"(content|node|article)", re.IGNORECASE))
        or soup.body
    )
    if article is None:
        return ""

    for tag in article.find_all(["nav", "script", "style", "aside", "header", "footer", "form"]):
        tag.decompose()

    text = article.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if "Descargar" in text:
        text = text.split("Descargar", 1)[1].lstrip()

    return text.strip()


def _format_article_txt(
    art: dict[str, Any],
    edicion: dict[str, Any],
    body: str,
) -> str:
    """Header con metadata fielmente arriba para que el LLM lo cite."""
    seccion_line = f"Sección: {art['seccion']}\n" if art.get("seccion") else ""
    edicion_label = (
        f"Edición N° {edicion.get('numero')} "
        f"(AÑO {edicion.get('anio_roman') or '?'})"
    )
    return (
        f"Fecha: {edicion.get('fecha_legible') or edicion.get('fecha') or 's/d'} "
        f"({edicion.get('fecha') or 's/d'})\n"
        f"Fuente: BCR Informativo Semanal — {edicion_label}\n"
        f"Título: {art['titulo']}\n"
        f"{seccion_line}"
        f"URL original: {art['url']}\n"
        f"Slug interno: {art['slug']}\n"
        f"\n"
        f"{body}\n"
    )


def _list_past_editions(html: str) -> list[dict[str, Any]]:
    """Parsea /ediciones-anteriores y devuelve dicts {numero, anio_roman,
    fecha, fecha_legible, url}. Permisivo: si el link no trae el número
    en su texto, lo intenta sacar del container; si igual no aparece,
    último recurso, infiere el número del slug (ej. 'ano-xlv-edicion').

    En este sitio, el número de edición NO siempre está en el link text;
    a veces el link es solo "AÑO XLV - Edición..." sin número, y el
    número está en un span aparte. Ser flexible importa más que estricto.
    """
    soup = BeautifulSoup(html, "html.parser")
    editions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=_EDITION_HREF_RE):
        href = link.get("href", "")
        if not href:
            continue
        if href in seen:
            continue
        seen.add(href)

        # Intento 1: el link text trae todo.
        link_text = link.get_text(" ", strip=True)
        meta = _parse_edition_heading(link_text)

        # Intento 2: si no, el container más cercano (suele tener fecha + título).
        container_text = ""
        if meta["numero"] is None or meta["fecha"] is None:
            container = link.find_parent(["article", "div", "li", "section"]) or link
            container_text = container.get_text(" ", strip=True)
            container_meta = _parse_edition_heading(container_text)
            for k, v in container_meta.items():
                if meta.get(k) is None and v is not None:
                    meta[k] = v

        # Aún sin número de edición tenemos un link válido — lo guardamos
        # igual (la metadata se completará al levantar la página de la
        # edición, que sí trae el heading completo).
        editions.append({**meta, "url": _absolute(href)})

    return editions


# ---------------------------------------------------------------------------
# Funciones públicas.
# ---------------------------------------------------------------------------
def _ingest_edition(
    db: Session,
    client: OpenAI,
    vs_id: str,
    edition_html: str,
    *,
    max_uploads: int,
) -> dict[str, Any]:
    """Ingesta los artículos nuevos de una edición ya levantada (HTML)."""
    parsed = _parse_edition_page(edition_html)
    candidates = parsed.get("articles", [])

    if not candidates:
        return {
            "edicion": {k: v for k, v in parsed.items() if k != "articles"},
            "in_page": 0,
            "new_found": 0,
            "uploaded": [],
            "failed": [],
        }

    already = {
        r.slug
        for r in db.query(IngestedInformativoArticle.slug)
        .filter(IngestedInformativoArticle.slug.in_([c["slug"] for c in candidates]))
        .all()
    }
    new_items = [c for c in candidates if c["slug"] not in already]

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for art in new_items[:max_uploads]:
        try:
            body = _fetch_article_body(art["url"])
            time.sleep(_POLITE_DELAY_S)
            if not body:
                failed.append({"slug": art["slug"], "error": "empty_body"})
                continue

            content = _format_article_txt(art, parsed, body)
            # Nombre legible para el archivo en OpenAI.
            fecha = parsed.get("fecha") or "sd"
            numero = parsed.get("numero") or 0
            filename = f"{fecha}_informativo_{numero}_{art['slug']}.txt"
            file_id = upload_text_file(client, vs_id, filename, content)

            db.add(IngestedInformativoArticle(
                slug=art["slug"],
                edicion_numero=parsed.get("numero"),
                edicion_anio_roman=parsed.get("anio_roman"),
                fecha=parsed.get("fecha") or "1900-01-01",
                fecha_legible=parsed.get("fecha_legible"),
                titulo=art["titulo"],
                seccion=art.get("seccion"),
                url=art["url"],
                openai_file_id=file_id,
                ingested_at=datetime.utcnow(),
            ))
            uploaded.append({
                "slug": art["slug"],
                "titulo": art["titulo"][:80],
                "seccion": art.get("seccion"),
                "openai_file_id": file_id,
            })
        except Exception as exc:  # noqa: BLE001
            failed.append({
                "slug": art["slug"],
                "error": f"{type(exc).__name__}: {exc}",
            })

    db.commit()

    return {
        "edicion": {k: v for k, v in parsed.items() if k != "articles"},
        "in_page": len(candidates),
        "new_found": len(new_items),
        "uploaded": uploaded,
        "failed": failed,
    }


def scrape_current_edition(
    db: Session,
    max_uploads: int = 20,
) -> dict[str, Any]:
    """Cron del viernes. Levanta la página vigente del informativo y sube
    todos los artículos nuevos al vector store."""
    started_at = datetime.utcnow()
    if not BOT_OPENAI_API_KEY:
        return {"status": "error", "stage": "config", "detail": "OPENAI_API_KEY no configurada"}

    try:
        html = _http_get(_CURRENT_EDITION_URL)
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "fetch_listing",
            "detail": str(exc),
            "started_at": started_at.isoformat(),
        }

    client = OpenAI(api_key=BOT_OPENAI_API_KEY)
    vs_id = ensure_vector_store_id(db, "informativo", client)

    result = _ingest_edition(db, client, vs_id, html, max_uploads=max_uploads)

    return {
        "status": "ok" if not result["failed"] else "partial",
        "vector_store_id": vs_id,
        **result,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
    }


def backfill_past_editions(
    db: Session,
    max_editions: int = _BACKFILL_DEFAULT_MAX_EDITIONS,
    max_articles_total: int = _BACKFILL_DEFAULT_MAX_ARTICLES,
    start_page: int = 0,
    pages_to_walk: int = 3,
) -> dict[str, Any]:
    """One-shot manual desde el admin endpoint. Recorre el listado paginado
    de ediciones anteriores (start_page..start_page+pages_to_walk) y para
    cada edición pasada que no tengamos ingestada, baja sus artículos y los
    sube. Cap por corrida con max_editions y max_articles_total.

    Tip de uso: corré varias veces con start_page=0, 3, 6, ... para ir
    avanzando hacia atrás en el tiempo sin colgar el server."""
    started_at = datetime.utcnow()
    if not BOT_OPENAI_API_KEY:
        return {"status": "error", "stage": "config", "detail": "OPENAI_API_KEY no configurada"}

    # 1. Listado paginado: recolectamos URLs de ediciones a procesar.
    edition_urls: list[dict[str, Any]] = []
    for page in range(start_page, start_page + pages_to_walk):
        url = _PAST_EDITIONS_URL if page == 0 else f"{_PAST_EDITIONS_URL}?page={page}"
        try:
            html = _http_get(url)
        except requests.RequestException as exc:
            return {
                "status": "error",
                "stage": "fetch_listing",
                "page": page,
                "detail": str(exc),
                "started_at": started_at.isoformat(),
            }
        editions = _list_past_editions(html)
        if not editions:
            break
        edition_urls.extend(editions)
        time.sleep(_POLITE_DELAY_S)

    if not edition_urls:
        return {
            "status": "ok",
            "detail": "No se encontraron ediciones en el rango pedido",
            "started_at": started_at.isoformat(),
        }

    client = OpenAI(api_key=BOT_OPENAI_API_KEY)
    vs_id = ensure_vector_store_id(db, "informativo", client)

    edition_results: list[dict[str, Any]] = []
    total_uploaded = 0

    for edition in edition_urls[:max_editions]:
        remaining = max_articles_total - total_uploaded
        if remaining <= 0:
            break

        try:
            html = _http_get(edition["url"])
            time.sleep(_POLITE_DELAY_S)
        except requests.RequestException as exc:
            edition_results.append({
                "url": edition["url"],
                "status": "fetch_failed",
                "detail": str(exc),
            })
            continue

        r = _ingest_edition(db, client, vs_id, html, max_uploads=remaining)
        edition_results.append({
            "url": edition["url"],
            "edicion": r.get("edicion"),
            "in_page": r.get("in_page"),
            "new_found": r.get("new_found"),
            "uploaded_count": len(r.get("uploaded", [])),
            "failed_count": len(r.get("failed", [])),
        })
        total_uploaded += len(r.get("uploaded", []))

    return {
        "status": "ok",
        "vector_store_id": vs_id,
        "pages_walked": pages_to_walk,
        "editions_found_in_listing": len(edition_urls),
        "editions_processed": min(max_editions, len(edition_urls)),
        "total_articles_uploaded": total_uploaded,
        "editions": edition_results,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
    }

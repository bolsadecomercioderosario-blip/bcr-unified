"""
Importador de WordPress (WXR) → módulo noticias.

Parsea el/los XML exportados desde WP (Herramientas → Exportar) y crea Noticias.
- Preserva el slug de WP (para poder armar redirects de las URLs viejas).
- Portada: toma la imagen destacada (_thumbnail_id → attachment) o, si no hay,
  la primera imagen del cuerpo.
- Categoría: mapea a nuestras CATEGORIAS (primera que matchee); ignora
  'Sin categorizar' y 'Destacadas' como primaria.

Nota sobre imágenes: en esta etapa las URLs siguen apuntando al host de WP
(masbcr.com.ar/wp-content). El re-hosting a Cloudinary es un paso aparte
(rehost) que conviene correr antes de dar de baja WordPress.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from noticias.models import CATEGORIAS

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
}
_OUR_CATS = set(CATEGORIAS)
_SKIP_CATS = {"Sin categorizar", "Destacadas"}
_IMG_RE = re.compile(r"https?://[^\s\"')]+?\.(?:jpg|jpeg|png|webp|gif)", re.I)


def _t(el, path) -> str:
    e = el.find(path, NS)
    return (e.text or "") if e is not None else ""


def _parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _attachment_map(roots: list[ET.Element]) -> dict[str, str]:
    """{post_id -> url} de todos los attachments (para resolver la portada)."""
    amap: dict[str, str] = {}
    for root in roots:
        for it in root.findall(".//item"):
            if _t(it, "wp:post_type") != "attachment":
                continue
            pid = _t(it, "wp:post_id")
            url = _t(it, "wp:attachment_url") or _t(it, "guid")
            if pid and url:
                amap[pid] = url
    return amap


def _post_categoria(item) -> str | None:
    cats = [c.text for c in item.findall("category") if c.get("domain") == "category" and c.text]
    for c in cats:
        if c in _OUR_CATS:
            return c
    for c in cats:
        if c not in _SKIP_CATS:
            return c
    return None


def _post_portada(item, amap: dict[str, str], body: str) -> str | None:
    # 1) imagen destacada
    for pm in item.findall("wp:postmeta", NS):
        if _t(pm, "wp:meta_key") == "_thumbnail_id":
            tid = _t(pm, "wp:meta_value")
            if tid in amap:
                return amap[tid]
    # 2) primera imagen del cuerpo
    m = _IMG_RE.search(body or "")
    return m.group(0) if m else None


def parse_wxr(paths: list[str]) -> list[dict[str, Any]]:
    roots = [ET.parse(p).getroot() for p in paths]
    amap = _attachment_map(roots)

    posts: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for root in roots:
        for it in root.findall(".//item"):
            if _t(it, "wp:post_type") != "post" or _t(it, "wp:status") != "publish":
                continue
            slug = _t(it, "wp:post_name").strip()
            titulo = (_t(it, "title") or "").strip()
            if not slug or slug == "hello-world" or titulo.lower() == "hello world!":
                continue
            if slug in seen_slugs:
                continue
            body = _t(it, "content:encoded")
            posts.append({
                "slug": slug,
                "titulo": titulo,
                "bajada": (_t(it, "excerpt:encoded") or "").strip() or None,
                "cuerpo": body or None,
                "categoria": _post_categoria(it),
                "imagen_portada": _post_portada(it, amap, body),
                "fecha_pub": _parse_date(_t(it, "wp:post_date")),
            })
            seen_slugs.add(slug)
    return posts


# ---------------------------------------------------------------------------
# Kit Multimedia: las galerías no están en el XML (son widgets Elementor).
# Se scrapean las 6 páginas del sitio original y se traen las imágenes full-size.
# ---------------------------------------------------------------------------
_KIT_PAGES = {
    "institucional": "https://masbcr.com.ar/kit-institucional/",
    "rosario": "https://masbcr.com.ar/kit-rosario/",
    "cultivos": "https://masbcr.com.ar/kit-cultivos/",
    "ganaderia": "https://masbcr.com.ar/kit-ganaderia/",
    "logistica": "https://masbcr.com.ar/kit-logistica/",
    "otras": "https://masbcr.com.ar/kit-otras/",
}
_UPLOAD_IMG_RE = re.compile(r"https?://[^\s\"')]+wp-content/uploads/[^\s\"')]+\.(?:jpg|jpeg|png)", re.I)


def _strip_accents_low(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _map_subcat(kit_cat: str, heading: str) -> str | None:
    """Mapea el título de sección del sitio a nuestra subcategoría (KIT_SUBCATS).
    Devuelve None si el heading no corresponde a una subcategoría conocida."""
    h = _strip_accents_low(heading)
    if kit_cat == "institucional":
        if "autoridad" in h or "funcionario" in h:
            return "Autoridades y funcionarios"
        if "edificio" in h or "instalacion" in h:
            return "Edificios e instalaciones"
    if kit_cat == "cultivos":
        if "soja" in h:
            return "Soja"
        if "trigo" in h:
            return "Trigo"
        if "maiz" in h:
            return "Maíz"
        if "otro" in h:
            return "Otros cultivos"
    return None


def _is_heading(el) -> bool:
    if el.name in ("h1", "h2", "h3", "h4"):
        return True
    cls = " ".join(el.get("class", []))
    return "elementor-heading-title" in cls


def scrape_kit_masbcr(db, reset: bool = False) -> dict[str, Any]:
    """Scrapea las 6 galerías del kit de masbcr y crea MediaAsset (URLs del host
    WP; se re-hostean después).

    Consciente de secciones: recorre cada página en orden y asigna cada imagen a
    la subcategoría del último título de sección (Institucional → Autoridades /
    Edificios; Cultivos → Soja/Trigo/Maíz/Otros si existieran). Dedup POR PÁGINA
    (no global), así una imagen que aparece en dos galerías queda en ambas.

    reset=True borra los MediaAsset antes de re-scrapear (estado limpio)."""
    import requests
    from bs4 import BeautifulSoup

    from noticias.models import MediaAsset

    headers = {"User-Agent": "Mozilla/5.0 (BCR importer)"}
    if reset:
        db.query(MediaAsset).delete()
        db.commit()

    # dedup por (categoría, url) contra lo ya existente en esa categoría.
    existentes: dict[str, set] = {}
    for cat, u in db.query(MediaAsset.kit_cat, MediaAsset.url).all():
        existentes.setdefault(cat, set()).add(u)

    resumen: dict[str, Any] = {}
    for slug, url in _KIT_PAGES.items():
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            resumen[slug] = {"error": str(exc)}
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        ya = existentes.setdefault(slug, set())
        cur_sub: str | None = None
        seen_page: set = set()
        nuevas = 0
        sub_count: dict[str, int] = {}
        orden = 0
        for el in soup.find_all(True):
            if _is_heading(el):
                txt = el.get_text(strip=True)
                if txt:
                    cur_sub = _map_subcat(slug, txt)
                continue
            if el.name == "a" and el.get("href"):
                h = el["href"]
                if not (_UPLOAD_IMG_RE.match(h) and not re.search(r"logo|logobolsa", h, re.I)):
                    continue
                if h in seen_page:
                    continue
                seen_page.add(h)
                if h in ya:
                    continue
                db.add(MediaAsset(kit_cat=slug, subcat=cur_sub, url=h, orden=orden))
                ya.add(h)
                orden += 1
                nuevas += 1
                key = cur_sub or "(sin clasificar)"
                sub_count[key] = sub_count.get(key, 0) + 1
        resumen[slug] = {"nuevas": nuevas, "por_subcat": sub_count}
    db.commit()
    return resumen


def importar_posts(db, posts: list[dict[str, Any]]) -> dict[str, Any]:
    """Crea las noticias que no existan (por slug). No pisa las existentes."""
    from noticias.models import Noticia

    existentes = {s for (s,) in db.query(Noticia.slug).all()}
    creados, saltados = 0, 0
    for p in posts:
        if p["slug"] in existentes:
            saltados += 1
            continue
        db.add(Noticia(
            slug=p["slug"], titulo=p["titulo"], bajada=p["bajada"], cuerpo=p["cuerpo"],
            imagen_portada=p["imagen_portada"], categoria=p["categoria"],
            estado="publicado", fecha_pub=p["fecha_pub"] or datetime.utcnow(),
        ))
        existentes.add(p["slug"])
        creados += 1
    db.commit()
    return {"total_en_xml": len(posts), "creados": creados, "saltados_ya_existian": saltados}

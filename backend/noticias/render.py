"""
Render server-side del sitio público Más BCR (SEO-friendly).

No usamos Jinja2 (no está en requirements): armamos el HTML con helpers y
f-strings. El CSS/estructura replican la identidad oficial de la guía de marca:
navy #00314b, cian #009ee3, tipografía Outfit, isologotipo +BCR.

Se sacaron del header el widget de clima y la lupita de búsqueda (pedido del
usuario).
"""
from __future__ import annotations

import html
from datetime import datetime
from urllib.parse import quote

from noticias.models import CATEGORIAS

_MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def fecha_es(dt: datetime | None) -> str:
    if not dt:
        return ""
    return f"{dt.day} de {_MESES[dt.month]} de {dt.year}"


_LOGO = (
    '<svg viewBox="0 0 100 100" aria-hidden="true">'
    '<g fill="#009ee3">'
    '<rect x="14" y="40" width="34" height="15"/>'
    '<rect x="33" y="14" width="15" height="41"/>'
    '<rect x="52" y="45" width="34" height="15"/>'
    '<rect x="52" y="45" width="15" height="41"/>'
    "</g></svg>"
)

_ICON = {
    "x": '<svg class="ico" viewBox="0 0 24 24"><path d="M18.9 2H22l-7 8 8.2 11h-6.4l-5-6.6L6 21H2.9l7.5-8.6L2.3 2h6.6l4.5 6zM17.8 19h1.7L7.3 3.8H5.5z"/></svg>',
    "ig": '<svg class="ico" viewBox="0 0 24 24"><path d="M12 2.2c3.2 0 3.6 0 4.9.07 3.3.15 4.8 1.7 5 5 .06 1.3.07 1.7.07 4.9s0 3.6-.07 4.9c-.15 3.3-1.7 4.8-5 5-1.3.06-1.7.07-4.9.07s-3.6 0-4.9-.07c-3.3-.15-4.8-1.7-5-5C2.05 15.6 2 15.2 2 12s0-3.6.07-4.9c.15-3.3 1.7-4.8 5-5C8.4 2.05 8.8 2 12 2.2zm0 3.2A6.6 6.6 0 1 0 18.6 12 6.6 6.6 0 0 0 12 5.4zm0 10.9A4.3 4.3 0 1 1 16.3 12 4.3 4.3 0 0 1 12 16.3zm6.8-11.1a1.55 1.55 0 1 1-1.55-1.55A1.55 1.55 0 0 1 18.8 5.2z"/></svg>',
    "fb": '<svg class="ico" viewBox="0 0 24 24"><path d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5H17V3.6c-.3 0-1.3-.1-2.5-.1-2.5 0-4.2 1.5-4.2 4.3v2.1H7.5V13h2.8v8z"/></svg>',
    "yt": '<svg class="ico" viewBox="0 0 24 24"><path d="M23 7.5a3 3 0 0 0-2.1-2.1C19 4.9 12 4.9 12 4.9s-7 0-8.9.5A3 3 0 0 0 1 7.5 31 31 0 0 0 .6 12 31 31 0 0 0 1 16.5a3 3 0 0 0 2.1 2.1c1.9.5 8.9.5 8.9.5s7 0 8.9-.5a3 3 0 0 0 2.1-2.1 31 31 0 0 0 .4-4.5 31 31 0 0 0-.4-4.5zM9.7 15.3V8.7l5.7 3.3z"/></svg>',
    "in": '<svg class="ico" viewBox="0 0 24 24"><path d="M4.98 3.5A2.5 2.5 0 1 1 5 8.5a2.5 2.5 0 0 1 0-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.8-2 3.7-2 4 0 4.7 2.6 4.7 6V21h-4v-5.3c0-1.3 0-2.9-1.8-2.9s-2 1.4-2 2.8V21H9z"/></svg>',
    "wa": '<svg class="ico" viewBox="0 0 24 24"><path d="M12 2a10 10 0 0 0-8.5 15.2L2 22l4.9-1.3A10 10 0 1 0 12 2zm0 18a8 8 0 0 1-4.1-1.1l-.3-.2-2.9.8.8-2.8-.2-.3A8 8 0 1 1 12 20zm4.4-6c-.2-.1-1.4-.7-1.6-.8s-.4-.1-.5.1-.6.8-.8 1-.3.2-.5.1a6.5 6.5 0 0 1-3.2-2.8c-.2-.4.2-.4.6-1.2a.5.5 0 0 0 0-.5c0-.1-.5-1.3-.7-1.7s-.4-.4-.5-.4h-.5a1 1 0 0 0-.7.3A3 3 0 0 0 6.8 10a5.3 5.3 0 0 0 1.1 2.8 12 12 0 0 0 4.6 4c2.2.9 2.2.6 2.6.6a2.6 2.6 0 0 0 1.7-1.2 2.1 2.1 0 0 0 .1-1.2c0-.1-.2-.2-.5-.3z"/></svg>',
    "mail": '<svg class="ico" viewBox="0 0 24 24"><path d="M2 5h20v14H2zm2 2v.5l8 5 8-5V7l-8 5z"/></svg>',
}

_CSS = """
:root{--navy:#00314b;--cyan:#009ee3;--link:#0079ad;--text:#333;--muted:#6b7280;--line:#e5e7eb;--f:"Outfit",system-ui,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--f);color:var(--text);background:#fff;line-height:1.55}
img{max-width:100%;display:block}
a{color:var(--link);text-decoration:none}
.wrap{max-width:1180px;margin:0 auto;padding:0 18px}
.ph{background:linear-gradient(135deg,#cdd6df,#9aa7b6);position:relative;overflow:hidden}
.ph img{width:100%;height:100%;object-fit:cover;position:absolute;inset:0}
.logo{display:flex;align-items:center;gap:12px}
.logo svg{width:38px;height:38px;flex:none}
.logo .txt{display:flex;flex-direction:column;line-height:1}
.logo .n{font-weight:800;font-size:22px;color:#fff;letter-spacing:.5px}
.logo .s{font-size:8.5px;letter-spacing:3px;color:var(--cyan);margin-top:4px;font-weight:600}
header.top{background:var(--navy);color:#fff;position:sticky;top:0;z-index:50}
.topbar{display:flex;align-items:center;gap:30px;height:76px}
nav.main{display:flex;gap:24px;align-items:center;font-weight:600;font-size:14px;position:relative}
nav.main a{color:#fff}
.drop{position:relative}
.drop>span{cursor:pointer}
.drop>span::after{content:" \\25BE";color:var(--cyan);font-size:11px}
.drop .menu{display:none;position:absolute;top:100%;left:0;background:#fff;min-width:210px;box-shadow:0 12px 30px rgba(0,0,0,.15);border-radius:6px;padding:6px 0;z-index:60}
.drop:hover .menu{display:block}
.drop .menu a{display:block;color:var(--navy);padding:9px 16px;font-size:13.5px}
.drop .menu a:hover{background:#f1f5f9}
.top-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.socials{display:flex;gap:11px}
.ico{width:15px;height:15px;fill:#fff;opacity:.9}
.hero{display:grid;grid-template-columns:1.35fr 1fr;background:var(--navy)}
.hero .img{aspect-ratio:16/10}
.hero .panel{padding:38px 40px;color:#fff;display:flex;flex-direction:column;justify-content:center}
.hero .k{color:var(--cyan);font-weight:700;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:12px}
.hero h1{font-weight:800;font-size:32px;line-height:1.18;margin-bottom:16px}
.hero h1 a{color:#fff}
.hero p{font-size:14.5px;color:#cdd8e0;margin-bottom:18px;font-weight:300}
.date{color:var(--cyan);font-size:13px;font-weight:600}
section.grid{padding:36px 0 50px}
.sec-title{font-weight:800;color:var(--navy);font-size:20px;margin:0 0 20px;border-left:4px solid var(--cyan);padding-left:12px}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:28px}
.card .img{aspect-ratio:16/10;border-top:3px solid var(--cyan)}
.card .k{color:var(--cyan);font-weight:700;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;margin:13px 0 6px}
.card h3{font-weight:700;color:var(--navy);font-size:18px;line-height:1.28}
.card h3 a{color:var(--navy)}
.card .d{color:var(--muted);font-size:12px;margin-top:9px}
.article-wrap{padding:36px 0 10px}
.art{display:grid;grid-template-columns:78px 1fr 300px;gap:26px}
.share{display:flex;flex-direction:column;gap:12px;padding-top:6px}
.share a{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--navy)}
.share .ico{width:16px;height:16px;opacity:1}
.art .k{color:var(--cyan);font-weight:700;font-size:12px;letter-spacing:1.2px;text-transform:uppercase;margin-bottom:10px}
.art h1{font-weight:800;color:var(--navy);font-size:36px;line-height:1.15;margin-bottom:14px}
.art .meta{color:var(--muted);font-size:13px;margin-bottom:18px}
.art .bajada{font-size:18px;color:#4b5563;margin-bottom:22px}
.art .cover{aspect-ratio:16/9;margin-bottom:22px;border-radius:4px}
.art .body{font-size:16px;color:#333}
.art .body p{margin-bottom:16px}
.art .body h2{color:var(--navy);font-size:24px;margin:24px 0 12px}
.art .body img{border-radius:4px;margin:16px 0}
.art .body a{color:var(--link);text-decoration:underline}
aside h4{font-weight:800;color:#9aa2b1;font-size:13px;letter-spacing:1.5px;border-bottom:2px solid var(--line);padding-bottom:8px;margin-bottom:14px}
.rel{display:flex;gap:11px;padding:11px 0;border-bottom:1px solid var(--line)}
.rel .t{width:58px;height:44px;flex:none;border-radius:3px}
.rel a{color:var(--navy);font-weight:600;font-size:13px;line-height:1.3}
footer{background:var(--navy);color:#b9c6d0;padding:36px 0;margin-top:30px}
.foot{display:flex;gap:48px;align-items:flex-start;flex-wrap:wrap}
.foot .col{font-size:13px;line-height:1.95}
.foot .col b{color:#fff}
.empty{text-align:center;color:var(--muted);padding:80px 20px}
.kit-intro{color:var(--muted);font-size:14px;max-width:780px;margin:-6px 0 24px}
.kitgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.kitcard{display:block;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff;transition:box-shadow .15s}
.kitcard:hover{box-shadow:0 10px 24px rgba(0,0,0,.08)}
.kitcard .kitimg{aspect-ratio:16/10;border-top:3px solid var(--cyan)}
.kitbody{padding:14px 16px}
.kitbody h3{color:var(--navy);font-weight:800;font-size:18px}
.kitbody p{color:var(--muted);font-size:13px;margin-top:6px}
.kitcount{display:inline-block;margin-top:10px;font-size:11px;font-weight:700;color:var(--cyan);text-transform:uppercase;letter-spacing:.5px}
.galgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
.gal{position:relative;display:block;aspect-ratio:4/3;border-radius:8px;overflow:hidden;background:#e5e7eb}
.gal img{width:100%;height:100%;object-fit:cover}
.gal span{position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent,rgba(0,49,75,.85));color:#fff;font-size:12px;font-weight:600;padding:18px 10px 8px;opacity:0;transition:.15s}
.gal:hover span{opacity:1}
.backlink{color:var(--link);font-weight:600;font-size:14px;display:inline-block;margin-bottom:6px}
@media(max-width:820px){.hero,.cards,.art,.kitgrid{grid-template-columns:1fr}.share{flex-direction:row}nav.main{display:none}}
"""


def _cat_menu() -> str:
    items = "".join(
        f'<a href="/noticias/categoria/{quote(c)}">{_esc(c)}</a>' for c in CATEGORIAS
    )
    return f'<div class="drop"><span>Categorías</span><div class="menu">{items}</div></div>'


def _header() -> str:
    socials = "".join(_ICON[k] for k in ("x", "ig", "fb", "yt", "in"))
    return f"""
<header class="top"><div class="wrap topbar">
  <a class="logo" href="/noticias/">{_LOGO}<span class="txt"><span class="n">+BCR</span><span class="s">FUENTE DE NOTICIAS</span></span></a>
  <nav class="main">
    <a href="#">Sobre Nosotros</a>
    {_cat_menu()}
    <a href="/noticias/kit">Kit Multimedia</a>
    <a href="#">Contacto</a>
  </nav>
  <div class="top-right"><div class="socials">{socials}</div></div>
</div></header>"""


def _footer() -> str:
    return f"""
<footer><div class="wrap foot">
  <a class="logo">{_LOGO}<span class="txt"><span class="n">+BCR</span><span class="s">FUENTE DE NOTICIAS</span></span></a>
  <div class="col"><b>Contacto</b><br>54-341-5258300<br>masbcr.com.ar</div>
  <div class="col"><b>Secciones</b><br>Sobre Nosotros<br>Categorías<br>Kit Multimedia<br>Contacto</div>
</div></footer>"""


def base_page(*, title: str, description: str, body: str, canonical: str,
              og_image: str | None = None, og_type: str = "website") -> str:
    og_img = f'<meta property="og:image" content="{_esc(og_image)}">' if og_image else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{_esc(canonical)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{_esc(canonical)}">
<meta property="og:site_name" content="Más BCR — Fuente de Noticias">
{og_img}
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head><body>
{_header()}
{body}
{_footer()}
</body></html>"""


def _img(url: str | None) -> str:
    if url:
        return f'<div class="ph img"><img src="{_esc(url)}" alt=""></div>'
    return '<div class="ph img"></div>'


def _card(n) -> str:
    return f"""<article class="card">
  <a href="/noticias/nota/{_esc(n.slug)}">{_img(n.imagen_portada)}</a>
  <div class="k">{_esc(n.categoria or "Noticias")}</div>
  <h3><a href="/noticias/nota/{_esc(n.slug)}">{_esc(n.titulo)}</a></h3>
  <div class="d">{fecha_es(n.fecha_pub)}</div>
</article>"""


def render_home(noticias: list) -> tuple[str, str]:
    """Devuelve (title, body_html) para la home."""
    if not noticias:
        body = '<div class="empty">Todavía no hay noticias publicadas.</div>'
        return "Más BCR — Fuente de Noticias", body

    hero = noticias[0]
    resto = noticias[1:13]
    hero_html = f"""
<div class="hero">
  <a class="img" href="/noticias/nota/{_esc(hero.slug)}">{_img(hero.imagen_portada)}</a>
  <div class="panel">
    <div class="k">{_esc(hero.categoria or "Noticias")}</div>
    <h1><a href="/noticias/nota/{_esc(hero.slug)}">{_esc(hero.titulo)}</a></h1>
    <p>{_esc((hero.bajada or "")[:220])}</p>
    <span class="date">{fecha_es(hero.fecha_pub)}</span>
  </div>
</div>"""
    cards = "".join(_card(n) for n in resto)
    grid = f'<section class="grid"><div class="wrap"><div class="cards">{cards}</div></div></section>' if resto else ""
    body = hero_html + grid
    return "Más BCR — Fuente de Noticias", body


def render_lista(titulo: str, noticias: list) -> str:
    if not noticias:
        inner = '<div class="empty">No hay noticias en esta sección.</div>'
    else:
        cards = "".join(_card(n) for n in noticias)
        inner = f'<div class="cards">{cards}</div>'
    return f'<section class="grid"><div class="wrap"><h2 class="sec-title">{_esc(titulo)}</h2>{inner}</div></section>'


_KIT_INTRO = (
    "Las imágenes y videos de esta biblioteca están a disposición de los medios de "
    "comunicación y son de libre uso. Se permite la descarga, publicación y libre "
    "edición del material de acuerdo a las buenas prácticas del periodismo."
)


def render_kit_index(cats: list[dict]) -> str:
    """cats: list de {slug, nombre, desc, thumb, count}."""
    cards = ""
    for c in cats:
        thumb = f'<img src="{_esc(c.get("thumb"))}" alt="">' if c.get("thumb") else ""
        cards += f"""<a class="kitcard" href="/noticias/kit/{_esc(c['slug'])}">
  <div class="ph kitimg">{thumb}</div>
  <div class="kitbody"><h3>{_esc(c['nombre'])}</h3><p>{_esc(c['desc'])}</p>
  <span class="kitcount">{c.get('count', 0)} archivos</span></div></a>"""
    return (f'<section class="grid"><div class="wrap">'
            f'<h2 class="sec-title">Kit Multimedia</h2>'
            f'<p class="kit-intro">{_KIT_INTRO}</p>'
            f'<div class="kitgrid">{cards}</div></div></section>')


def render_kit_gallery(nombre: str, assets: list) -> str:
    if not assets:
        inner = '<div class="empty">Esta galería todavía no tiene imágenes.</div>'
    else:
        items = ""
        for a in assets:
            items += (f'<a class="gal" href="{_esc(a.url)}" target="_blank" rel="noopener" download>'
                      f'<img src="{_esc(a.url)}" alt="{_esc(a.titulo or "")}">'
                      f'<span>&#10515; Descargar</span></a>')
        inner = f'<div class="galgrid">{items}</div>'
    return (f'<section class="grid"><div class="wrap">'
            f'<a class="backlink" href="/noticias/kit">&#8592; Kit Multimedia</a>'
            f'<h2 class="sec-title">{_esc(nombre)}</h2>{inner}</div></section>')


def render_article(n, relacionadas: list, canonical: str) -> str:
    # Botones de compartir con la URL canónica.
    u = quote(canonical, safe="")
    t = quote(n.titulo, safe="")
    share = f"""
<div class="share">
  <a target="_blank" rel="noopener" href="https://www.facebook.com/sharer/sharer.php?u={u}">{_ICON['fb']}</a>
  <a target="_blank" rel="noopener" href="https://twitter.com/intent/tweet?url={u}&text={t}">{_ICON['x']}</a>
  <a target="_blank" rel="noopener" href="https://www.linkedin.com/sharing/share-offsite/?url={u}">{_ICON['in']}</a>
  <a target="_blank" rel="noopener" style="background:#25d366" href="https://wa.me/?text={t}%20{u}">{_ICON['wa']}</a>
  <a href="mailto:?subject={t}&body={u}" style="background:#6b7280">{_ICON['mail']}</a>
</div>"""

    rels = ""
    for r in relacionadas:
        rels += f"""<div class="rel"><a class="t" href="/noticias/nota/{_esc(r.slug)}">{_img(r.imagen_portada)}</a><a href="/noticias/nota/{_esc(r.slug)}">{_esc(r.titulo)}</a></div>"""
    aside = f'<aside><h4>NOTAS RELACIONADAS</h4>{rels}</aside>' if rels else "<aside></aside>"

    cover = (
        f'<div class="ph cover"><img src="{_esc(n.imagen_portada)}" alt=""></div>'
        if n.imagen_portada else ""
    )
    bajada = f'<p class="bajada">{_esc(n.bajada)}</p>' if n.bajada else ""

    body = f"""
<div class="article-wrap"><div class="wrap art">
  {share}
  <div class="content">
    <div class="k">{_esc(n.categoria or "Noticias")}</div>
    <h1>{_esc(n.titulo)}</h1>
    <div class="meta">{fecha_es(n.fecha_pub)}</div>
    {bajada}
    {cover}
    <div class="body">{n.cuerpo or ""}</div>
  </div>
  {aside}
</div></div>"""
    return body

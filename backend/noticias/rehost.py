"""
Re-hosting de imágenes a Cloudinary (independencia de WordPress).

Las notas migradas de WP y las fotos del Kit apuntan a masbcr.com.ar/wp-content.
Este módulo las sube a Cloudinary (que las baja del origen) y reemplaza la URL en
la DB, para poder dar de baja WordPress.

- Idempotente: usa un public_id determinístico (hash de la URL origen) con
  overwrite=False → si ya se subió, Cloudinary devuelve la existente (dedup, sin
  re-bajar). Las URLs que ya son de Cloudinary se saltean.
- Se procesa en lotes (limit) para no exceder el timeout del request; se llama
  repetidamente hasta que `restantes` llega a 0.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import or_

# Sólo imágenes del WordPress de masbcr (no links externos como PDFs de rosgan).
_WP_IMG = re.compile(
    r"https?://[^\s\"')]*masbcr\.com\.ar/wp-content/uploads/[^\s\"')]+?\.(?:jpg|jpeg|png|webp|gif)",
    re.I,
)
# Patrón SQL para seleccionar sólo lo re-hosteable (imágenes de masbcr).
_LIKE_WP = "%masbcr.com.ar/wp-content%"


def _to_cloudinary(url: str) -> str | None:
    """Sube `url` (remota) a Cloudinary y devuelve la secure_url; None si falla.
    Determinístico e idempotente por public_id = hash de la URL origen."""
    if not url or "res.cloudinary.com" in url:
        return url  # ya está en Cloudinary
    # El origen fuerza https (http hace 301 y Cloudinary no sigue el redirect).
    src = re.sub(r"^http://", "https://", url)
    try:
        import cloudinary.uploader
        pid = "masbcr-rehost/" + hashlib.md5(src.encode("utf-8")).hexdigest()
        res = cloudinary.uploader.upload(
            src, public_id=pid, overwrite=False, resource_type="image",
        )
        return res.get("secure_url")
    except Exception as exc:  # noqa: BLE001
        print(f"[rehost] fallo subiendo {url}: {type(exc).__name__}: {exc}")
        return None


def _rewrite_body(html: str, errores: list) -> tuple[str, int]:
    """Reemplaza en el HTML del cuerpo cada imagen wp-content por su equivalente
    en Cloudinary. Devuelve (html_nuevo, cantidad_reemplazada)."""
    urls = set(_WP_IMG.findall(html or ""))
    n = 0
    for u in urls:
        nu = _to_cloudinary(u)
        if nu and nu != u:
            html = html.replace(u, nu)
            n += 1
        elif not nu:
            errores.append(u)
    return html, n


def rehost_batch(db, limit: int = 25) -> dict[str, Any]:
    """Re-hostea un lote. Primero el Kit (1 imagen por registro), después las
    notas (portada + cuerpo). Devuelve conteos y cuánto queda."""
    from noticias.models import MediaAsset, Noticia

    errores: list = []
    kit_ok = 0
    notas_ok = 0
    imgs = 0

    # --- Kit ---
    kit = (db.query(MediaAsset)
           .filter(MediaAsset.url.like(_LIKE_WP))
           .limit(limit).all())
    for m in kit:
        nu = _to_cloudinary(m.url)
        if nu and nu != m.url:
            m.url = nu
            kit_ok += 1
            imgs += 1
        elif not nu:
            errores.append(m.url)
    db.commit()

    # --- Notas (con lo que quede del cupo) ---
    rest = max(0, limit - len(kit))
    if rest:
        notas = (db.query(Noticia)
                 .filter(or_(Noticia.imagen_portada.like(_LIKE_WP),
                             Noticia.cuerpo.like(_LIKE_WP)))
                 .limit(rest).all())
        for n in notas:
            changed = False
            if n.imagen_portada and "masbcr.com.ar/wp-content" in n.imagen_portada:
                nu = _to_cloudinary(n.imagen_portada)
                if nu and nu != n.imagen_portada:
                    n.imagen_portada = nu
                    imgs += 1
                    changed = True
                elif not nu:
                    errores.append(n.imagen_portada)
            if n.cuerpo and "masbcr.com.ar/wp-content" in n.cuerpo:
                nuevo, c = _rewrite_body(n.cuerpo, errores)
                if c:
                    n.cuerpo = nuevo
                    imgs += c
                    changed = True
            if changed:
                notas_ok += 1
        db.commit()

    rem_kit = db.query(MediaAsset).filter(MediaAsset.url.like(_LIKE_WP)).count()
    rem_notas = (db.query(Noticia)
                 .filter(or_(Noticia.imagen_portada.like(_LIKE_WP),
                             Noticia.cuerpo.like(_LIKE_WP)))
                 .count())
    return {
        "kit_rehosteadas": kit_ok,
        "notas_tocadas": notas_ok,
        "imagenes_subidas": imgs,
        "errores": len(errores),
        "restantes": {"kit": rem_kit, "notas": rem_notas},
    }

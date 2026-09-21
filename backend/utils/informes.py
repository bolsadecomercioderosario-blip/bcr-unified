"""
Scraping de los informes del informativo semanal de la BCR.

Cada artículo (ej. https://www.bcr.com.ar/.../noticias-informativo-semanal-106)
expone título y copete a través de los meta tags Open Graph:

    <meta property="og:title" content="..." />
    <meta property="og:description" content="..." />

Eso evita parsear el HTML completo y es estable frente a cambios de plantilla.
"""
import requests
from bs4 import BeautifulSoup

from common import assert_safe_url

# El informativo semanal siempre vive en el sitio de la BCR. Restringimos el
# scrape a ese dominio (anti-SSRF): no tiene sentido bajar URLs arbitrarias.
_ALLOWED_HOSTS = {"bcr.com.ar", "www.bcr.com.ar"}


class InformeNotFound(Exception):
    """La URL no respondió 200 o no expone los meta tags og: esperados."""


def fetch_informe(url: str, timeout: float = 15.0) -> dict:
    """Descarga la página y extrae título + copete.

    Returns:
        dict con keys: titulo, copete, url
    Raises:
        InformeNotFound si la URL no es accesible o no expone og:title/og:description.
    """
    assert_safe_url(url, allowed_hosts=_ALLOWED_HOSTS)  # anti-SSRF + solo bcr.com.ar
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BCRSemanaDatos/1.0)"}
    try:
        r = requests.get(url, timeout=timeout, headers=headers)
        r.raise_for_status()
    except requests.RequestException as e:
        raise InformeNotFound(f"No se pudo acceder a la URL: {e}") from e

    soup = BeautifulSoup(r.text, "html.parser")
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")

    if not og_title or not og_title.get("content"):
        raise InformeNotFound("La página no expone og:title")
    if not og_desc or not og_desc.get("content"):
        raise InformeNotFound("La página no expone og:description")

    return {
        "titulo": og_title["content"].strip(),
        "copete": og_desc["content"].strip(),
        "url": url,
    }

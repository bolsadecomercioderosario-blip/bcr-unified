"""
Wrapper para publicar en X (Twitter) en nombre de @BolsaRosario.

Usa OAuth 1.0a con las 4 credenciales en env vars:
    X_API_KEY            - "API Key" (consumer key)
    X_API_KEY_SECRET     - "API Key Secret" (consumer secret)
    X_ACCESS_TOKEN       - "Access Token"
    X_ACCESS_TOKEN_SECRET- "Access Token Secret"

Para tweets largos (>280 chars) la API respeta el privilegio Premium de la
cuenta — no hace falta hacer hilo manualmente.

Para tweets con imagen, X requiere 2 pasos:
  1) subir el archivo con la API v1.1 (`media_upload`)
  2) publicar el tweet con la API v2 (`create_tweet`) referenciando el media_id

El módulo expone una sola función pública: `post_tweet`.
"""
import os
from typing import Optional

import tweepy


class TwitterNotConfigured(Exception):
    """Faltan una o más env vars X_*."""


def _credentials() -> dict:
    """Devuelve las 4 credenciales o lanza si falta alguna."""
    keys = ("X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
    creds = {k: os.environ.get(k) for k in keys}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise TwitterNotConfigured(
            f"Falta(n) la(s) env var(s): {', '.join(missing)}. "
            "Configurá las 4 X_* en Render → Environment."
        )
    return creds


def _api_v1() -> tweepy.API:
    """Cliente v1.1 — sólo lo necesitamos para subir media."""
    c = _credentials()
    auth = tweepy.OAuth1UserHandler(
        c["X_API_KEY"], c["X_API_KEY_SECRET"],
        c["X_ACCESS_TOKEN"], c["X_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


def _client_v2() -> tweepy.Client:
    """Cliente v2 — para postear tweets."""
    c = _credentials()
    return tweepy.Client(
        consumer_key=c["X_API_KEY"],
        consumer_secret=c["X_API_KEY_SECRET"],
        access_token=c["X_ACCESS_TOKEN"],
        access_token_secret=c["X_ACCESS_TOKEN_SECRET"],
    )


def post_tweet(text: str, image_path: Optional[str] = None) -> dict:
    """Publica un tweet (opcionalmente con una imagen) en nombre de la cuenta
    asociada al token. Devuelve {tweet_id, url}.

    Args:
        text: contenido del tweet.
        image_path: path local a una imagen (jpg/png/webp) o None.

    Raises:
        TwitterNotConfigured: si faltan env vars.
        tweepy.TweepyException: si la API rechaza la operación.
    """
    if not text or not text.strip():
        raise ValueError("El texto del tweet no puede estar vacío")

    media_ids = []
    if image_path:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"No existe la imagen: {image_path}")
        media = _api_v1().media_upload(filename=image_path)
        media_ids.append(media.media_id_string)

    client = _client_v2()
    response = client.create_tweet(
        text=text,
        media_ids=media_ids or None,
    )

    tweet_id = response.data["id"]
    # Sin usuario en la URL funciona igual — X redirige a la URL canónica.
    return {
        "tweet_id": tweet_id,
        "url": f"https://x.com/i/web/status/{tweet_id}",
    }

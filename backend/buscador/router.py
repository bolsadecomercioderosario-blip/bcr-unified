"""
Router del Buscador con IA — `/api/buscar`.

Endpoint público que recibe una consulta en lenguaje natural + la lista
de destinos posibles (la mantiene el POC en su JS, único source of truth)
y devuelve los 1-3 destinos más relevantes usando un LLM como router.

Es público (sin require_auth) porque lo llama el POC estático en
bcr-portal-poc.onrender.com — no podemos pedirle bearer token.
Lo protegemos con rate limit por IP y validando que el LLM solo
devuelva URLs que estaban en el payload original (anti-alucinación).
"""
from __future__ import annotations

import json
import os
import time
import unicodedata
from collections import deque
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from openai import OpenAI
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/buscar", tags=["buscador"])

# Cliente perezoso: si no hay OPENAI_API_KEY el módulo igual carga, solo
# fallan los requests reales (con un 503 claro).
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="Servicio de IA no configurado (falta OPENAI_API_KEY)",
            )
        _client = OpenAI()
    return _client


# --- Rate limit: 30 requests por minuto por IP ----------------------------
RATE_LIMIT = 30
RATE_WINDOW = 60
_rate: dict[str, deque[float]] = {}
_rate_lock = Lock()


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        dq = _rate.setdefault(ip, deque())
        while dq and dq[0] < now - RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            return True
        dq.append(now)
        return False


# --- Cache en memoria por query normalizada -------------------------------
_cache: dict[str, list[dict]] = {}
_cache_lock = Lock()
_CACHE_MAX = 500


def _norm_query(q: str) -> str:
    nfkd = unicodedata.normalize("NFKD", q)
    ascii_q = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_q.lower().split())


# --- Schemas --------------------------------------------------------------
class DestinoIn(BaseModel):
    t: str = Field(..., max_length=200)
    d: str = Field(..., max_length=300)
    u: str = Field(..., max_length=500)


class BuscarPayload(BaseModel):
    q: str = Field(..., min_length=1, max_length=200)
    destinos: list[DestinoIn] = Field(..., min_length=1, max_length=100)


# --- Prompt ---------------------------------------------------------------
_SYSTEM_PROMPT = """Sos un router de búsqueda para el sitio de la Bolsa de Comercio de Rosario (BCR).
Recibís una consulta en lenguaje natural y una lista de destinos posibles (cada uno con título, descripción y URL).
Tu trabajo: elegir los 1-3 destinos MÁS relevantes para la consulta del usuario, ordenados por relevancia.

Respondé EXCLUSIVAMENTE con JSON con esta forma:
{"matches": [{"u": "url-exacta-del-destino", "t": "titulo-exacto-del-destino", "reason": "frase breve"}]}

Reglas:
- Devolvé las URLs y títulos EXACTOS como aparecen en la lista, sin modificar.
- 'reason' es una frase corta en español (máximo 12 palabras) que justifica por qué este destino responde la consulta.
- Máximo 3 destinos en la respuesta.
- Si ningún destino es claramente relevante, devolvé {"matches": []}.
- No incluyas texto fuera del JSON."""


@router.post("")
def buscar(payload: BuscarPayload, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(
            status_code=429,
            detail="Demasiadas consultas. Esperá unos segundos.",
        )

    q_norm = _norm_query(payload.q)
    with _cache_lock:
        if q_norm in _cache:
            return {"matches": _cache[q_norm], "cached": True}

    destinos_text = "\n".join(
        f"- {d.t}: {d.d} → {d.u}" for d in payload.destinos
    )
    user_msg = (
        f"Consulta del usuario: {payload.q}\n\n"
        f"Destinos disponibles:\n{destinos_text}"
    )

    try:
        completion = _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0.2,
            timeout=10,
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        matches = parsed.get("matches", [])
        if not isinstance(matches, list):
            matches = []
        # Anti-alucinación: solo dejamos pasar URLs que estaban en el payload.
        valid_urls = {d.u for d in payload.destinos}
        matches = [
            m for m in matches
            if isinstance(m, dict) and m.get("u") in valid_urls
        ][:3]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[buscador] error LLM: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Servicio de IA temporalmente no disponible",
        )

    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[q_norm] = matches

    return {"matches": matches, "cached": False}

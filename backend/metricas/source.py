"""
Fuente de datos del módulo Métricas.

Soporta dos orígenes y los normaliza a una misma forma:
  - Google Sheet publicado como CSV (fuente preferida). Se configura con la env
    var METRICAS_SHEET_CSV_URL (el link de "Archivo → Compartir → Publicar en la
    web → CSV"). Se cachea en memoria con TTL para no pegarle a Google en cada
    request.
  - Base de datos (fallback). Se usa si no hay Sheet configurado, o si el fetch
    del Sheet falla y no hay cache previo.

El catálogo de programas (slug, nombre, ícono, color, descripción, orden) vive
en seed_data.PROGRAMAS. El Sheet sólo aporta las filas de instancias; la columna
"programa" se matchea contra ese catálogo por nombre o slug. Si aparece un
programa desconocido, se crea una entrada ad-hoc para que igual se vea.

Forma normalizada que devuelve load():
    {
      "programas":  [ {id, slug, nombre, descripcion, icono, color, orden}, ... ],
      "instancias": [ {id, programa_id, titulo, anio, fecha, fecha_texto,
                       modalidad, localidades, personas, proyectos, osc,
                       escuelas, mentores, monto, ganadores, reconocimiento,
                       notas, orden}, ... ],
      "source": "sheet" | "db",
    }
"""
from __future__ import annotations

import csv
import io
import os
import re
import time
import unicodedata
import urllib.request

from .seed_data import PROGRAMAS as PROGRAMAS_CATALOG


SHEET_CSV_URL = os.environ.get("METRICAS_SHEET_CSV_URL", "").strip()
SHEET_EDIT_URL = os.environ.get("METRICAS_SHEET_EDIT_URL", "").strip()
SHEET_TTL = int(os.environ.get("METRICAS_SHEET_TTL", "120"))  # segundos

INT_FIELDS = ("anio", "personas", "proyectos", "osc", "escuelas", "mentores")
FLOAT_FIELDS = ("monto",)
TEXT_FIELDS = ("titulo", "fecha_texto", "modalidad", "localidades",
               "ganadores", "reconocimiento", "notas")

# Cache en memoria: {"data": <normalized>, "ts": <epoch>}
_cache: dict = {}


def sheet_configured() -> bool:
    return bool(SHEET_CSV_URL)


# --------------------------- helpers de parseo ----------------------------
def _norm(s: str) -> str:
    """Normaliza para matchear: sin acentos, minúsculas, sin espacios extra."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def _slugify(nombre: str) -> str:
    base = _norm(nombre)
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "programa"


def _to_int(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    # Tolera separadores de miles ("1.077", "1 077", "2,339").
    s = s.replace(".", "").replace(",", "").replace(" ", "")
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else None


def _to_float(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    # Quita separadores de miles, deja un punto decimal si lo hubiera.
    s = s.replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def _to_date_iso(v):
    """Devuelve 'YYYY-MM-DD' si puede parsear; si no, None."""
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)  # ISO
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)  # dd/mm/yyyy
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


# --------------------------- catálogo de programas ------------------------
def _catalog():
    """Devuelve (lista_programas_con_id, lookup_por_clave_normalizada)."""
    programas = []
    lookup = {}
    for i, p in enumerate(sorted(PROGRAMAS_CATALOG, key=lambda x: x["orden"]), start=1):
        entry = {
            "id": i, "slug": p["slug"], "nombre": p["nombre"],
            "descripcion": p.get("descripcion", ""), "icono": p.get("icono", ""),
            "color": p.get("color", "#0ea5e9"), "orden": p.get("orden", i),
        }
        programas.append(entry)
        lookup[_norm(p["slug"])] = entry
        lookup[_norm(p["nombre"])] = entry
    return programas, lookup


# --------------------------- lectura del Sheet ----------------------------
def _fetch_csv(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "bcr-metricas/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    return raw.decode("utf-8-sig", errors="replace")


def _parse_sheet(text: str) -> dict:
    # Detecta el delimitador: Google publica CSV con coma, pero toleramos punto
    # y coma (como el export de Excel en locale AR).
    head = text.split("\n", 1)[0]
    delim = ";" if head.count(";") > head.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    # Mapa de headers reales (normalizados) → nombre real de la columna.
    headers = {_norm(h): h for h in (reader.fieldnames or [])}

    def col(row, key):
        real = headers.get(key)
        return row.get(real, "") if real else ""

    programas, lookup = _catalog()
    extra_idx = len(programas)
    instancias = []
    n = 0
    for row in reader:
        titulo = (col(row, "titulo") or "").strip()
        prog_raw = (col(row, "programa") or "").strip()
        # Salta filas vacías (sin título ni programa).
        if not titulo and not prog_raw:
            continue

        prog = lookup.get(_norm(prog_raw))
        if not prog:
            # Programa desconocido: lo agregamos ad-hoc para no perder el dato.
            extra_idx += 1
            prog = {
                "id": extra_idx, "slug": _slugify(prog_raw), "nombre": prog_raw or "Sin programa",
                "descripcion": "", "icono": "📌", "color": "#94a3b8", "orden": 100 + extra_idx,
            }
            programas.append(prog)
            lookup[_norm(prog_raw)] = prog

        n += 1
        inst = {
            "id": n, "programa_id": prog["id"],
            "titulo": titulo or "(sin título)",
            "fecha": _to_date_iso(col(row, "fecha")),
            "orden": _to_int(col(row, "orden")) or n,
        }
        for f in INT_FIELDS:
            inst[f] = _to_int(col(row, f))
        for f in FLOAT_FIELDS:
            inst[f] = _to_float(col(row, f))
        for f in TEXT_FIELDS:
            if f == "titulo":
                continue
            inst[f] = (col(row, f) or "").strip()
        instancias.append(inst)

    return {"programas": programas, "instancias": instancias, "source": "sheet"}


def _load_sheet_cached(fresh: bool = False) -> dict | None:
    """Devuelve datos del Sheet (cacheados). None si falla y no hay cache."""
    now = time.time()
    if not fresh and _cache.get("data") and (now - _cache.get("ts", 0)) < SHEET_TTL:
        return _cache["data"]
    try:
        text = _fetch_csv(SHEET_CSV_URL)
        data = _parse_sheet(text)
        _cache["data"] = data
        _cache["ts"] = now
        return data
    except Exception as e:
        print(f"[metricas] Error leyendo el Sheet: {e}")
        # Servimos el último cache bueno si existe; si no, None → fallback DB.
        return _cache.get("data")


# --------------------------- lectura de la DB -----------------------------
def _load_db(db) -> dict:
    from .models import Instancia, Programa

    progs = (
        db.query(Programa)
        .order_by(Programa.orden, Programa.id)
        .all()
    )
    programas = [{
        "id": p.id, "slug": p.slug, "nombre": p.nombre,
        "descripcion": p.descripcion or "", "icono": p.icono or "",
        "color": p.color or "#0ea5e9", "orden": p.orden or 0,
    } for p in progs]

    insts = (
        db.query(Instancia)
        .order_by(Instancia.anio.asc().nullslast(), Instancia.orden.asc(), Instancia.id.asc())
        .all()
    )
    instancias = [{
        "id": i.id, "programa_id": i.programa_id, "titulo": i.titulo,
        "anio": i.anio, "fecha": i.fecha.isoformat() if i.fecha else None,
        "fecha_texto": i.fecha_texto or "", "modalidad": i.modalidad or "",
        "localidades": i.localidades or "", "personas": i.personas,
        "proyectos": i.proyectos, "osc": i.osc, "escuelas": i.escuelas,
        "mentores": i.mentores, "monto": i.monto, "ganadores": i.ganadores or "",
        "reconocimiento": i.reconocimiento or "", "notas": i.notas or "",
        "orden": i.orden or 0,
    } for i in insts]

    return {"programas": programas, "instancias": instancias, "source": "db"}


# --------------------------- API pública del módulo -----------------------
def load(db=None, fresh: bool = False) -> dict:
    """Carga normalizada. Prioriza el Sheet; cae a la DB si no hay Sheet o falla."""
    if sheet_configured():
        data = _load_sheet_cached(fresh=fresh)
        if data is not None:
            return data
    return _load_db(db)

"""
Parser de la planilla de Agenda de la Fundación BCR (Google Sheet).

La planilla es un documento humano: bloques por mes en orden DESCENDENTE
(agosto arriba → marzo abajo), cada bloque con una fila-título de mes
("agosto 2026"), una fila de encabezado ("Día, Evento, Equipo, metricas") y
luego las filas de actividades. Entre actividades hay filas en blanco.

Imperfecciones toleradas:
  - Algún bloque viene SIN la fila-título de mes (sólo con el encabezado "Día").
    Como el orden es descendente, se infiere ese mes como (mes_anterior - 1).
  - Filas en blanco salteadas.
  - La hora suele venir embebida en el texto del evento ("10:30 a 11:30 hs – …",
    "15 h: …"); se intenta extraer a un campo `hora` sin perder el texto.

`parse_rows(text)` devuelve una lista de dicts normalizados:
  {dia, mes, anio, fecha (ISO 'YYYY-MM-DD' o None), hora, evento, equipo, metricas}
ordenada cronológicamente (más viejo primero).
"""
from __future__ import annotations

import csv
import io
import re

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Hora al principio del evento. Captura rangos ("08:00 a 12:00 hs"), horas sueltas
# ("15 h", "10.30 h", "16:30 hs") y el separador que suele seguir (– / : / .).
_HORA_RE = re.compile(
    r"^\s*("
    r"\d{1,2}(?:[:.]\d{2})?\s*(?:a|-|–|—|y)\s*\d{1,2}(?:[:.]\d{2})?\s*(?:h|hs|horas)\b"  # rango
    r"|\d{1,2}(?:[:.]\d{2})?\s*(?:h|hs|horas)\b"                                          # suelta
    r")"
    r"\s*[.:–—-]?\s*",
    re.IGNORECASE,
)


def _mes_de(s: str):
    """(num_mes, anio|None) si la celda es un título de mes; None si no."""
    t = (s or "").strip().lower()
    if not t or t[:1].isdigit():
        return None
    for nombre, num in MESES.items():
        if t.startswith(nombre):
            y = re.search(r"(20\d\d)", t)
            return num, (int(y.group(1)) if y else None)
    return None


def _norm_time(h: str) -> str:
    """Normaliza la hora extraída: minúsculas, 'hs', puntos→dos puntos."""
    h = re.sub(r"\s+", " ", (h or "").strip())
    h = h.replace(".", ":")
    h = re.sub(r"\bhoras\b", "hs", h, flags=re.IGNORECASE)
    h = re.sub(r"\bh\b", "hs", h, flags=re.IGNORECASE)
    h = re.sub(r"\bHS\b", "hs", h)
    return h.strip(" .:–—-")


def _split_hora(evento: str):
    """(hora, evento_sin_hora). Si no hay hora al inicio, hora='' y evento igual."""
    ev = (evento or "").strip()
    m = _HORA_RE.match(ev)
    if not m:
        return "", ev
    hora = _norm_time(m.group(1))
    resto = ev[m.end():].strip(" .:–—-").strip()
    # Si al sacar la hora no queda nada, dejamos el evento original.
    return hora, (resto or ev)


def parse_rows(text: str) -> list[dict]:
    rdr = list(csv.reader(io.StringIO(text)))
    cur_mes = None
    cur_anio = None
    label_just_set = False
    out = []

    for row in rdr:
        if not row:
            continue
        c0 = (row[0] or "").strip()
        resto_vacio = not any((c or "").strip() for c in row[1:])
        if not c0 and resto_vacio:
            continue  # fila en blanco

        # ¿Título de mes?
        m = _mes_de(c0)
        if m:
            cur_mes, y = m
            if y:
                cur_anio = y
            label_just_set = True
            continue

        # ¿Encabezado de columnas ("Día, Evento, …")?
        if c0.lower() in ("dia", "día"):
            # Nuevo bloque. Si no vino precedido por un título de mes, inferimos
            # el mes como el anterior - 1 (la planilla va en orden descendente).
            if not label_just_set and cur_mes:
                cur_mes -= 1
                if cur_mes == 0:
                    cur_mes = 12
                    cur_anio = (cur_anio - 1) if cur_anio else None
            label_just_set = False
            continue

        # ¿Fila de actividad? (col0 = día numérico)
        mdia = re.match(r"^(\d{1,2})\b", c0)
        if not mdia:
            continue
        dia = int(mdia.group(1))
        evento = (row[1].strip() if len(row) > 1 else "")
        equipo = (row[2].strip() if len(row) > 2 else "")
        metricas = (row[3].strip() if len(row) > 3 else "")
        if not evento and not equipo and not metricas:
            continue  # día sin contenido

        hora, evento_limpio = _split_hora(evento)
        fecha = None
        if cur_anio and cur_mes and 1 <= dia <= 31:
            try:
                from datetime import date
                fecha = date(cur_anio, cur_mes, dia).isoformat()
            except ValueError:
                fecha = None

        out.append({
            "dia": dia, "mes": cur_mes, "anio": cur_anio, "fecha": fecha,
            "hora": hora, "evento": evento_limpio, "equipo": equipo,
            "metricas": metricas,
        })

    # Orden cronológico (los que no tienen fecha, al final por su mes/día aprox).
    def _key(r):
        return (r["anio"] or 0, r["mes"] or 0, r["dia"] or 0, r["hora"] or "")
    out.sort(key=_key)
    return out

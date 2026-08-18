# Módulo `canciones` — Encuesta versión B (solo canciones)

Variante del módulo [`corte`](../corte/README.md): la misma encuesta para armar
la versión reducida de "El Más Acá", pero mostrando **solo las canciones /
números musicales** (se excluyen las 10 intervenciones) y **sin el campo tipo**
en las tarjetas. Módulo aparte para no tocar la versión A, que sigue viva.

## URLs

| URL | Quién | Qué |
|---|---|---|
| `/canciones/` | Murguistas (link de WhatsApp) | Encuesta: nombre + 15 canciones con contador en vivo |
| `/canciones/resultados?k=TOKEN` | Organizador | Ranking de canciones por votos + calculadora de duración |

Mecánica idéntica a `corte`: roster fijo de 20 murguistas, una respuesta por
persona (nombre tomado tras enviar; reintento → 409), contador en vivo y en
resultados el ranking + calculadora + botón de reset.

**Objetivo/máximo propios**: como acá se eligen sólo canciones (el resto del
show reducido son intervenciones), el objetivo es **~22/23'** y el máximo **25'**
(`OBJETIVO_SEG` / `MAX_SEG` en `data.py`). Las zonas del contador se calculan
relativas a esos valores.

## Datos

Las 15 canciones (con duraciones y grupos) están en [`data.py`](data.py). Los
`id` se conservan iguales a los del módulo `corte` (por eso hay saltos: faltan
los ids de las intervenciones). Total de todas las canciones: 43:26.

## Variable de entorno

| Variable | Default (dev) | Prod |
|---|---|---|
| `CANCIONES_TOKEN` | `canciones2026` | Seteala en Render para los resultados. |

Tabla propia `canciones_respuestas` (independiente de la versión A). Se crea sola
al arrancar.

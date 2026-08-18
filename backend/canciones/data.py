"""
Datos para la versión B de la encuesta: SOLO las canciones / números musicales
de "El Más Acá" (sin las intervenciones). Sin campo `tipo` para simplificar.

Los ids se conservan iguales a los del módulo `corte` (fuente original), por
eso hay saltos (faltan los ids de las intervenciones). No importa: acá son sólo
claves estables de cada canción.
"""

# Objetivo y máximo (en segundos). Versión B: sólo canciones ~22/23'; el resto
# del tiempo del show reducido se usa para las intervenciones.
OBJETIVO_SEG = 23 * 60   # 23:00
MAX_SEG = 25 * 60        # 25:00


# Roster de murguistas (mismo que la versión A). Orden alfabético.
NOMBRES = [
    "Brandon", "Cabe", "Cacha", "Charo", "Chimi", "Desi", "Elías", "Fabio",
    "Fermín", "Gabi H", "Gabi M", "Joaqui", "Juanma", "Lucas", "Martín",
    "Mica", "Santi", "Tacho", "Vir1", "Vir2",
]


# Grupos narrativos, en orden de aparición.
GRUPOS = [
    {"id": "apertura",  "label": "Apertura"},
    {"id": "primero",   "label": "Primer bloque"},
    {"id": "habitos",   "label": "Buenos hábitos"},
    {"id": "fantasmas", "label": "Fantasmas / Macabra"},
    {"id": "funeraria", "label": "Funeraria · trámites · última voluntad"},
    {"id": "final",     "label": "Final"},
]


def _m(mm, ss):
    return mm * 60 + ss


# Sólo canciones (se excluyen las intervenciones). id estable.
BLOQUES = [
    {"id": 1,  "grupo": "apertura",  "nombre": "Clarinada + Presentación",                    "dur": _m(4, 18)},

    {"id": 3,  "grupo": "primero",   "nombre": "Alegorías de la muerte",                       "dur": _m(0, 55)},
    {"id": 5,  "grupo": "primero",   "nombre": "Salpicón",                                     "dur": _m(3, 19)},

    {"id": 7,  "grupo": "habitos",   "nombre": "Buenos Hábitos – Busca lo más vital + Bacilos", "dur": _m(1, 45)},
    {"id": 8,  "grupo": "habitos",   "nombre": "Chacarera / Puente carretero",                 "dur": _m(1, 12)},
    {"id": 10, "grupo": "habitos",   "nombre": "Churros vs. Manzanas + canciones de cancha",   "dur": _m(4, 25)},
    {"id": 11, "grupo": "habitos",   "nombre": "Reflexión Buenos Hábitos",                     "dur": _m(2, 30)},

    {"id": 13, "grupo": "fantasmas", "nombre": "Cuplé de los Fantasmas",                       "dur": _m(4, 40)},
    {"id": 15, "grupo": "fantasmas", "nombre": "Macabra + reflexión política (Reina Batata + Razón de vivir + Témpano)", "dur": _m(5, 10)},

    {"id": 17, "grupo": "funeraria", "nombre": "Caballero",                                    "dur": _m(1, 50)},
    {"id": 19, "grupo": "funeraria", "nombre": "Animaniacs / Trámites",                        "dur": _m(1, 15)},
    {"id": 21, "grupo": "funeraria", "nombre": "Último Deseo",                                 "dur": _m(1, 50)},

    {"id": 23, "grupo": "final",     "nombre": "Canción Final",                                "dur": _m(2, 45)},
    {"id": 24, "grupo": "final",     "nombre": "Retirada",                                     "dur": _m(5, 35)},
    {"id": 25, "grupo": "final",     "nombre": "Pre-bajada (Árbol + Abel Pintos) / Bajada",     "dur": _m(1, 57)},
]


BLOQUES_POR_ID = {b["id"]: b for b in BLOQUES}


def duracion_de(ids):
    return sum(BLOQUES_POR_ID[i]["dur"] for i in ids if i in BLOQUES_POR_ID)

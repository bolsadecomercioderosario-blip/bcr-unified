"""
Datos del espectáculo "El Más Acá" para la encuesta de la versión reducida.

Fuente única de verdad: los bloques con su duración (en segundos) y el grupo
narrativo al que pertenecen. El frontend los pide por /api/corte/bloques y los
resultados se calculan contra estas mismas duraciones (nunca se confía en el
total que manda el cliente).
"""

# Objetivo y máximo de la versión reducida (en segundos).
OBJETIVO_SEG = 30 * 60   # 30:00
MAX_SEG = 35 * 60        # 35:00


# Grupos narrativos, en orden de aparición en el espectáculo.
GRUPOS = [
    {"id": "apertura",  "label": "Apertura"},
    {"id": "primero",   "label": "Primer bloque"},
    {"id": "habitos",   "label": "Buenos hábitos"},
    {"id": "fantasmas", "label": "Fantasmas / Macabra"},
    {"id": "funeraria", "label": "Funeraria · trámites · última voluntad"},
    {"id": "final",     "label": "Final"},
]


def _m(mm, ss):
    """Minutos:segundos → segundos."""
    return mm * 60 + ss


# Bloques del espectáculo, en orden. id estable (no cambiar: es la clave que se
# guarda en las respuestas). dur en segundos.
BLOQUES = [
    {"id": 1,  "grupo": "apertura",  "nombre": "Clarinada + Presentación",                    "tipo": "Canción · Apertura",   "dur": _m(4, 18)},

    {"id": 2,  "grupo": "primero",   "nombre": "Intervención 1 – Personaje, radio y pitonisa", "tipo": "Intervención",         "dur": _m(4, 55)},
    {"id": 3,  "grupo": "primero",   "nombre": "Alegorías de la muerte",                       "tipo": "Canción",              "dur": _m(0, 55)},
    {"id": 4,  "grupo": "primero",   "nombre": "Intervención 2 – Radio / canciones sobre la muerte", "tipo": "Intervención",  "dur": _m(1, 1)},
    {"id": 5,  "grupo": "primero",   "nombre": "Salpicón",                                     "tipo": "Canción",              "dur": _m(3, 19)},

    {"id": 6,  "grupo": "habitos",   "nombre": "Intervención 3 – Médico",                      "tipo": "Intervención",         "dur": _m(1, 20)},
    {"id": 7,  "grupo": "habitos",   "nombre": "Buenos Hábitos – Busca lo más vital + Bacilos", "tipo": "Canción",             "dur": _m(1, 45)},
    {"id": 8,  "grupo": "habitos",   "nombre": "Chacarera / Puente carretero",                 "tipo": "Canción",              "dur": _m(1, 12)},
    {"id": 9,  "grupo": "habitos",   "nombre": "Intervención 4 – Churros y manzanas",          "tipo": "Intervención",         "dur": _m(2, 8)},
    {"id": 10, "grupo": "habitos",   "nombre": "Churros vs. Manzanas + canciones de cancha",   "tipo": "Cuplé",                "dur": _m(4, 25)},
    {"id": 11, "grupo": "habitos",   "nombre": "Reflexión Buenos Hábitos",                     "tipo": "Canción · Reflexión",  "dur": _m(2, 30)},

    {"id": 12, "grupo": "fantasmas", "nombre": "Intervención 5 – Contacto con el más allá",    "tipo": "Intervención",         "dur": _m(4, 0)},
    {"id": 13, "grupo": "fantasmas", "nombre": "Cuplé de los Fantasmas",                       "tipo": "Cuplé",                "dur": _m(4, 40)},
    {"id": 14, "grupo": "fantasmas", "nombre": "Intervención 6 – Fantasmas / Bum Bum / vocales", "tipo": "Intervención",       "dur": _m(2, 35)},
    {"id": 15, "grupo": "fantasmas", "nombre": "Macabra + reflexión política (Reina Batata + Razón de vivir + Témpano)", "tipo": "Canción · Bloque", "dur": _m(5, 10)},

    {"id": 16, "grupo": "funeraria", "nombre": "Intervención 7A – Llegada de la funeraria",    "tipo": "Intervención",         "dur": _m(1, 40)},
    {"id": 17, "grupo": "funeraria", "nombre": "Caballero",                                    "tipo": "Canción",              "dur": _m(1, 50)},
    {"id": 18, "grupo": "funeraria", "nombre": "Intervención 7B – Cajones / CURDA",            "tipo": "Intervención",         "dur": _m(1, 10)},
    {"id": 19, "grupo": "funeraria", "nombre": "Animaniacs / Trámites",                        "tipo": "Canción",              "dur": _m(1, 15)},
    {"id": 20, "grupo": "funeraria", "nombre": "Intervención 7C – Formulario / última voluntad", "tipo": "Intervención",       "dur": _m(0, 55)},
    {"id": 21, "grupo": "funeraria", "nombre": "Último Deseo",                                 "tipo": "Canción",              "dur": _m(1, 50)},

    {"id": 22, "grupo": "final",     "nombre": "Intervención 8 – Resolución personaje/pitonisa", "tipo": "Intervención",       "dur": _m(4, 45)},
    {"id": 23, "grupo": "final",     "nombre": "Canción Final",                                "tipo": "Canción",              "dur": _m(2, 45)},
    {"id": 24, "grupo": "final",     "nombre": "Retirada",                                     "tipo": "Canción · Retirada",   "dur": _m(5, 35)},
]


# Índice id → bloque, para calcular totales server-side.
BLOQUES_POR_ID = {b["id"]: b for b in BLOQUES}


def duracion_de(ids):
    """Suma (en segundos) de los bloques cuyos ids se pasan. Ignora ids inválidos."""
    return sum(BLOQUES_POR_ID[i]["dur"] for i in ids if i in BLOQUES_POR_ID)

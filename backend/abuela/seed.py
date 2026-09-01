"""
Importación inicial de los datos de los Excels de la murga (caja, ensayos,
toques) a las tablas `ab_`. Corre una sola vez, cuando ab_murguistas está vacía.
Los datos vienen de seed_data.json (generado desde los Excels).
"""
import json
import os
import re
import unicodedata

from database import SessionLocal
from abuela import models as m

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSON = os.path.join(_DIR, "seed_data.json")


# Roster actual (orden, apodo canónico, nombre completo).
ROSTER = [
    ("Santi", "Santiago Raimondo"),
    ("Juanma", "Juan Manuel Gallichio"),
    ("Gabi H", "Gabriela Herrero"),
    ("Gabi M", "Gabriela Brun"),
    ("Lucas", "Lucas Suárez"),
    ("Joaqui", "Joaquina Palmieri"),
    ("Desi", "Desireé Marlene"),
    ("Vir1", "Virginia Gallicchio"),
    ("Vir2", "Virginia Steffanini"),
    ("Charo", "Charo Velázquez"),
    ("Mica", "Micaela Díaz"),
    ("Tincho", "Martín Vitta"),
    ("Fabio", "Fabio Latorre"),
    ("Fermín", "Fermín Pico Monti"),
    ("Cacha", "Cristian Rodríguez"),
    ("Chimi", "Juan Chiummiento"),
    ("Tacho", "Mauro Zeiter"),
    ("Brandon", "Brandon Piedrabuena"),
    ("Elías", "Elías C. Mateo"),
    ("Cabe", "Emmanuel Silvestre"),
]


def _norm(s):
    """minúsculas, sin acentos, sin prefijo de cuerda (ej 'SB- ', 'D - ')."""
    s = (s or "").strip()
    s = re.sub(r"^[A-Za-z]{1,3}\s*-\s*", "", s)  # saca 'D - ', 'PL- ', 'SB- '...
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().strip()


# Alias (normalizados) → apodo canónico del roster.
_ALIAS = {
    "santi": "Santi", "santiago": "Santi",
    "juan": "Juanma", "juanma": "Juanma", "juan manuel": "Juanma", "juanm": "Juanma",
    "gabi": "Gabi H", "gabriela": "Gabi H", "gabi h": "Gabi H",
    "gabi m": "Gabi M", "gabymar": "Gabi M", "gabriela brun": "Gabi M",
    "lucas": "Lucas",
    "joaqui": "Joaqui", "joaquina": "Joaqui",
    "desi": "Desi", "desiree": "Desi",
    "vir": "Vir1", "vir1": "Vir1", "virginia gallicchio": "Vir1",
    "vir2": "Vir2", "virginia steffanini": "Vir2",
    "charo": "Charo",
    "mica": "Mica",
    "tincho": "Tincho", "martin vitta": "Tincho", "martin": "Tincho",
    "fabio": "Fabio",
    "fermin": "Fermín",
    "cacha": "Cacha",
    "chimi": "Chimi", "juan chimi": "Chimi",
    "tacho": "Tacho",
    "brandon": "Brandon",
    "elias": "Elías",
    "cabe": "Cabe",
    # históricos (se crean inactivos, con estos nombres de display)
    "lauti": "Lauti", "lautaro": "Lauti", "leslie": "Leslie", "maru": "Maru",
    "marto": "Marto", "martin silberman": "Marto",
    "valen": "Valen", "valentin": "Valen",
    "lucio": "Lucio", "derian": "Derian", "jesi": "Jesi",
}
_ACTIVOS = {apodo for apodo, _ in ROSTER}


def _resolver(nombre, registro):
    """Devuelve el apodo canónico para un nombre de los Excels. Si no está en el
    roster, lo registra como histórico (inactivo) usando su nombre limpio."""
    n = _norm(nombre)
    if n in _ALIAS:
        apodo = _ALIAS[n]
    else:
        apodo = re.sub(r"^[A-Za-z]{1,3}\s*-\s*", "", (nombre or "").strip()) or nombre
    # Todo lo que no sea del roster activo se registra como histórico.
    if apodo not in _ACTIVOS:
        registro.setdefault(apodo, apodo)
    return apodo


def seed_abuela_if_empty():
    db = SessionLocal()
    try:
        if db.query(m.Murguista).count() > 0:
            print("Seed Abuela saltado (ya hay murguistas).")
            return
        if not os.path.exists(_JSON):
            print("Seed Abuela: no se encontró seed_data.json, se crea solo el roster.")
            data = {}
        else:
            with open(_JSON, encoding="utf-8") as f:
                data = json.load(f)

        historicos = {}  # display -> display (se completa al resolver nombres)

        # --- Caja ---
        for mv in data.get("caja_movimientos", []):
            db.add(m.CajaMov(fecha=mv["fecha"], cuenta=mv["cuenta"], tipo=mv["tipo"],
                             monto=mv["monto"], concepto=mv["concepto"], proyectado=False))
        for mv in data.get("caja_proyeccion", []):
            db.add(m.CajaMov(fecha=mv.get("fecha", ""), cuenta="", tipo=mv["tipo"],
                             monto=mv["monto"], concepto=mv["concepto"], proyectado=True))

        # --- Remeras ---
        rem = data.get("remeras", {})
        for nom in rem.get("pago", []):
            db.add(m.Remera(nombre=nom, pago=True))
        for nom in rem.get("no_pago", []):
            db.add(m.Remera(nombre=nom, pago=False))

        # --- Toques con asistencia (Sheet2) ---
        orden = 0
        for t in data.get("toques_asistencia", []):
            orden += 1
            tq = m.Toque(nombre=(t.get("lugar") or t.get("fecha") or "Toque"),
                         fecha=t.get("fecha", ""), lugar=t.get("lugar", ""),
                         evento=t.get("evento", ""), condicion_eco=t.get("condicion", ""),
                         orden=orden)
            db.add(tq); db.flush()
            for nom, subio in (t.get("asistencia") or {}).items():
                ap = _resolver(nom, historicos)
                db.add(m.ToqueAsist(toque_id=tq.id, nombre=ap, subio=bool(subio)))

        # --- Toques ficha (Didi) ---
        def pick(ficha, *claves):
            for k, v in ficha.items():
                kn = _norm(k)
                for c in claves:
                    if c in kn:
                        return v
            return ""
        for t in data.get("toques_didi", []):
            orden += 1
            f = t.get("ficha", {})
            db.add(m.Toque(
                nombre=t.get("nombre", ""), lugar=pick(f, "lugar"),
                duracion=pick(f, "duracion", "tiempo"), horario=pick(f, "horario", "convocatoria"),
                sonido=pick(f, "sonido") if "prueba" not in _norm(pick(f, "sonido") or "") else "",
                prueba_sonido=pick(f, "prueba"), camarin=pick(f, "camarin"),
                cachet=pick(f, "cachet", "retribu"), factura=pick(f, "factura"),
                entradas=pick(f, "entrada"), viaticos=pick(f, "viatico"),
                comida=pick(f, "comida"), bebida=pick(f, "bebida"), otros=pick(f, "otros"),
                contacto=pick(f, "contacto"), encargado=pick(f, "encargado"),
                repertorio=pick(f, "repertorio"), orden=orden))

        # --- Ensayos (asistencia) ---
        for p in data.get("ensayos", []):
            periodo = p["periodo"]
            # fechas que efectivamente tienen alguna marca
            con_marcas = set()
            for integ in p["integrantes"]:
                con_marcas.update((integ.get("marcas") or {}).keys())
            fechas_orden = [fx for fx in p.get("fechas", []) if fx and fx in con_marcas]
            # completar con las que quedaron sin orden explícito
            for fx in con_marcas:
                if fx and fx not in fechas_orden:
                    fechas_orden.append(fx)
            fecha_to_ensayo = {}
            for i, fx in enumerate(fechas_orden):
                en = m.Ensayo(periodo=periodo, fecha=fx, orden=i)
                db.add(en); db.flush()
                fecha_to_ensayo[fx] = en.id
            for integ in p["integrantes"]:
                ap = _resolver(integ["nombre"], historicos)
                for fx, code in (integ.get("marcas") or {}).items():
                    eid = fecha_to_ensayo.get(fx)
                    if not eid:
                        continue
                    cod = (code or "").strip().upper()
                    if cod == "MT":
                        cod = "M"
                    if cod not in m.PUNTAJE:
                        continue
                    db.add(m.EnsayoAsist(ensayo_id=eid, nombre=ap, codigo=cod))

        # --- Roster (activos + históricos detectados) ---
        for i, (apodo, completo) in enumerate(ROSTER):
            db.add(m.Murguista(nombre=apodo, nombre_completo=completo, activo=True, orden=i))
        extra = 100
        for disp in sorted(historicos):
            if disp in _ACTIVOS:
                continue
            db.add(m.Murguista(nombre=disp, nombre_completo="", activo=False, orden=extra))
            extra += 1

        db.commit()
        print("Seed Abuela: datos de la murga importados (caja, ensayos, toques, roster).")
    except Exception as e:
        print(f"Error en seed Abuela: {e}")
        db.rollback()
    finally:
        db.close()

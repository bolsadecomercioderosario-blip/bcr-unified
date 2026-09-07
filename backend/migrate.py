"""
Migraciones idempotentes — corren en cada arranque del server.

OJO con Postgres: si un ALTER TABLE falla dentro de una transaction, la
transaction queda "aborted" y CUALQUIER query posterior en esa misma conexión
falla con "current transaction is aborted, commands ignored until end of
transaction block". Por eso cada operación usa su PROPIA conexión — si una
falla, la siguiente arranca limpia.
"""
from sqlalchemy import text
from database import engine, SessionLocal


def _try_exec(label, sql, expect_rowcount=False):
    """Corre `sql` en una conexión nueva. Si falla, se ignora y se sigue.
    Cada llamada es transactionalmente independiente — no contagia errores
    a las siguientes."""
    try:
        with engine.connect() as conn:
            res = conn.execute(text(sql))
            conn.commit()
            if expect_rowcount:
                print(f"  [OK] {label}: {res.rowcount} fila(s).")
            else:
                print(f"  [OK] {label}.")
    except Exception as e:
        # Truncamos el mensaje porque algunos drivers son verbosos.
        msg = str(e).split('\n')[0][:200]
        print(f"  [SKIP] {label}: ({msg}).")


def migrate():
    print("Iniciando migración de base de datos...")

    # --- Nuevas columnas (idempotente: si ya existen, el ALTER falla y se ignora) ---
    _try_exec(
        "ALTER add image_url",
        "ALTER TABLE activities ADD COLUMN image_url VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add order_index",
        "ALTER TABLE activities ADD COLUMN order_index INTEGER DEFAULT 0",
    )
    _try_exec(
        "ALTER add block_type",
        "ALTER TABLE activities ADD COLUMN block_type VARCHAR DEFAULT NULL",
    )
    _try_exec(
        "ALTER add origen",
        "ALTER TABLE activities ADD COLUMN origen VARCHAR DEFAULT 'comunicacion'",
    )
    _try_exec(
        "ALTER add comunicacion_notes",
        "ALTER TABLE activities ADD COLUMN comunicacion_notes VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add estado",
        "ALTER TABLE activities ADD COLUMN estado VARCHAR DEFAULT 'Pendiente'",
    )
    _try_exec(
        "ALTER add sec_responsible",
        "ALTER TABLE activities ADD COLUMN sec_responsible VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add sec_responsible_other",
        "ALTER TABLE activities ADD COLUMN sec_responsible_other VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add attachment_url",
        "ALTER TABLE activities ADD COLUMN attachment_url VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add attachment_name",
        "ALTER TABLE activities ADD COLUMN attachment_name VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add end_date",
        "ALTER TABLE activities ADD COLUMN end_date VARCHAR DEFAULT ''",
    )
    _try_exec(
        "ALTER add end_time",
        "ALTER TABLE activities ADD COLUMN end_time VARCHAR DEFAULT ''",
    )
    # Soft-delete / Archivados. DEFAULT FALSE deja en false las filas existentes
    # (no NULL), así el filtro `archived == False` no las esconde.
    _try_exec(
        "ALTER add archived",
        "ALTER TABLE activities ADD COLUMN archived BOOLEAN DEFAULT FALSE",
    )
    _try_exec(
        "ALTER add archived_at",
        "ALTER TABLE activities ADD COLUMN archived_at VARCHAR DEFAULT ''",
    )

    # --- Backfill de block_type desde el viejo flag observations='FIXED_BLOCK' ---
    # Idempotente: sólo toca filas que todavía no tengan block_type seteado.
    # is_custom: en SQLite es INTEGER (0/1), en Postgres es BOOLEAN. Usamos
    # comparación contra string para que ambos dialectos lo evalúen bien.
    _try_exec(
        "Backfill bloques 'fixed' (legacy observations=FIXED_BLOCK)",
        "UPDATE activities SET block_type='fixed', observations='' "
        "WHERE is_custom AND observations = 'FIXED_BLOCK' "
        "AND (block_type IS NULL OR block_type = '')",
        expect_rowcount=True,
    )
    _try_exec(
        "Backfill bloques 'variable' (resto de is_custom sin block_type)",
        "UPDATE activities SET block_type='variable' "
        "WHERE is_custom AND (block_type IS NULL OR block_type = '')",
        expect_rowcount=True,
    )

    backfill_origen_from_channel()

    seed_efemerides_if_empty()
    seed_metricas_if_empty()

    # Columnas nuevas del módulo Aapresid (tablero simplificado)
    _try_exec("ALTER aap_shifts add responsible_name",
              "ALTER TABLE aap_shifts ADD COLUMN responsible_name VARCHAR DEFAULT ''")
    _try_exec("ALTER aap_meetings add area_name",
              "ALTER TABLE aap_meetings ADD COLUMN area_name VARCHAR DEFAULT ''")
    _try_exec("ALTER aap_meetings add responsible_name",
              "ALTER TABLE aap_meetings ADD COLUMN responsible_name VARCHAR DEFAULT ''")

    from aapresid.seed import seed_aapresid_if_empty
    seed_aapresid_if_empty()

    # Panel interno de la murga: importa los datos de los Excels (caja, ensayos,
    # toques) la primera vez que las tablas ab_ están vacías.
    from abuela.seed import seed_abuela_if_empty
    seed_abuela_if_empty()
    normalizar_fechas_toques()
    limpiar_import_abuela()
    reasignar_derian_a_brandon()


def reasignar_derian_a_brandon():
    """En el Excel de asistencia, la fila "Derian" era en realidad Brandon. Sus
    marcas se cargan a Brandon, ensayo por ensayo: sólo se agregan en los
    ensayos donde Brandon todavía NO tiene marca (así no pisa lo que se haya
    cargado a mano). Idempotente: al re-correr, los que ya están se saltean.
    Lee del seed_data.json original (Derian ya fue borrado de la DB)."""
    import json
    import os
    from abuela.models import Ensayo, EnsayoAsist

    db = SessionLocal()
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abuela", "seed_data.json")
        if not os.path.exists(path):
            return
        data = json.load(open(path, encoding="utf-8"))
        der = {}
        for p in data.get("ensayos", []):
            for integ in p.get("integrantes", []):
                if (integ.get("nombre") or "").strip().lower() == "derian":
                    for fx, code in (integ.get("marcas") or {}).items():
                        der[fx] = code
        if not der:
            return
        # Ensayos donde Brandon ya tiene marca (para no pisarlos).
        brandon_eids = {a.ensayo_id for a in db.query(EnsayoAsist).filter(EnsayoAsist.nombre == "Brandon").all()}
        fecha_ids = {}
        for e in db.query(Ensayo).all():
            fecha_ids.setdefault(e.fecha, []).append(e.id)
        agregadas = 0
        for fx, code in der.items():
            cod = (code or "").strip().upper()
            if cod == "MT":
                cod = "M"
            if cod not in ("P", "T", "M", "A", "X"):
                continue
            for eid in fecha_ids.get(fx, []):
                if eid in brandon_eids:
                    continue  # Brandon ya tiene marca en ese ensayo (respeta lo manual)
                db.add(EnsayoAsist(ensayo_id=eid, nombre="Brandon", codigo=cod))
                brandon_eids.add(eid)
                agregadas += 1
        if agregadas:
            db.commit()
            print(f"Reasignacion Derian->Brandon: {agregadas} marcas agregadas a Brandon.")
    except Exception as e:
        print(f"Error reasignando Derian->Brandon: {e}")
        db.rollback()
    finally:
        db.close()


def limpiar_import_abuela():
    """Limpieza de la importación de los Excels viejos (una sola vez):
    borra los ex-integrantes (inactivos) con todas sus marcas, y los ensayos
    con fecha rota (sin fecha real / la mal parseada 2026-12-30). Se dispara
    sólo mientras existan integrantes inactivos; una vez limpio, no hace nada.
    """
    import re
    from abuela.models import Murguista, EnsayoAsist, ToqueAsist, Ensayo

    db = SessionLocal()
    try:
        inactivos = db.query(Murguista).filter(Murguista.activo == False).all()  # noqa: E712
        if not inactivos:
            return  # ya está limpio
        nombres = [x.nombre for x in inactivos]

        marcas_ens = db.query(EnsayoAsist).filter(EnsayoAsist.nombre.in_(nombres)).delete(synchronize_session=False)
        marcas_toq = db.query(ToqueAsist).filter(ToqueAsist.nombre.in_(nombres)).delete(synchronize_session=False)
        for x in inactivos:
            db.delete(x)

        rotos = [e for e in db.query(Ensayo).all()
                 if not re.match(r"^\d{4}-\d{2}-\d{2}$", (e.fecha or "")) or (e.fecha == "2026-12-30")]
        reids = [e.id for e in rotos]
        marcas_rotas = 0
        if reids:
            marcas_rotas = db.query(EnsayoAsist).filter(
                EnsayoAsist.ensayo_id.in_(reids)).delete(synchronize_session=False)
            for e in rotos:
                db.delete(e)

        db.commit()
        print(f"Limpieza import Abuela: {len(nombres)} ex-integrantes + {marcas_ens + marcas_toq} marcas suyas; "
              f"{len(reids)} ensayos rotos ({marcas_rotas} marcas).")
    except Exception as e:
        print(f"Error en limpieza de import Abuela: {e}")
        db.rollback()
    finally:
        db.close()


def normalizar_fechas_toques():
    """Deja las fechas de los toques en formato DD/MM/AAAA (las que vienen en
    ISO del Excel). Idempotente: las que ya están DD/MM/AAAA o son texto raro
    (sin año) se dejan igual."""
    import re
    from abuela.models import Toque

    iso = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
    db = SessionLocal()
    try:
        cambiadas = 0
        for t in db.query(Toque).all():
            mt = iso.match((t.fecha or "").strip())
            if mt:
                nueva = f"{mt.group(3)}/{mt.group(2)}/{mt.group(1)}"
                if nueva != t.fecha:
                    t.fecha = nueva
                    cambiadas += 1
            # Algunos toques (import "Didi") traen una fecha metida en el campo
            # Lugar (la celda "Lugar y fecha" era una fecha): la movemos a fecha.
            ml = iso.match((t.lugar or "").strip())
            if ml:
                if not (t.fecha or "").strip():
                    t.fecha = f"{ml.group(3)}/{ml.group(2)}/{ml.group(1)}"
                t.lugar = ""
                cambiadas += 1
            # Otros "Didi" traen la fecha como texto libre al inicio del Lugar
            # (ej "14/1, Rosario (Parque Urquiza)" o "Pj 19/12"). La separamos:
            # fecha = DD/MM(/AAAA), y el resto queda como Lugar.
            if not (t.fecha or "").strip():
                txt = re.match(
                    r"^\s*([A-Za-zÀ-ÿ.]{1,4}\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b[\s,.\-]*(.*)$",
                    (t.lugar or "").strip())
                if txt:
                    pref = (txt.group(1) or "").strip()
                    parts = txt.group(2).split("/")
                    dd, mm = parts[0].zfill(2), parts[1].zfill(2)
                    if len(parts) == 3:
                        yy = parts[2]
                        yy = ("20" + yy) if len(yy) == 2 else yy
                        t.fecha = f"{dd}/{mm}/{yy}"
                    else:
                        t.fecha = f"{dd}/{mm}"
                    resto = txt.group(3).strip().strip(",.-").strip()
                    t.lugar = (pref + " " + resto).strip() if pref else resto
                    cambiadas += 1
            # Normalizar cualquier fecha tipo D/M o D/M/AA a DD/MM(/AAAA).
            mf = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", (t.fecha or "").strip().rstrip(" :;,.-"))
            if mf:
                dd, mm = mf.group(1).zfill(2), mf.group(2).zfill(2)
                if mf.group(3):
                    yy = mf.group(3)
                    yy = ("20" + yy) if len(yy) == 2 else yy
                    nf = f"{dd}/{mm}/{yy}"
                else:
                    nf = f"{dd}/{mm}"
                if nf != (t.fecha or ""):
                    t.fecha = nf
                    cambiadas += 1
        if cambiadas:
            db.commit()
        print(f"Normalización fechas toques: {cambiadas} corregidas.")
    except Exception as e:
        print(f"Error normalizando fechas de toques: {e}")
        db.rollback()
    finally:
        db.close()


def backfill_origen_from_channel():
    """Migra el viejo canal "Agenda Compromisos" al nuevo campo `origen`.

    Las actividades que tenían ese canal pasan a origen='secretaria' (son la
    Agenda de Compromisos) y se les saca el canal de la lista, porque el
    casillero se eliminó del formulario. El resto queda en 'comunicacion' (el
    default de la columna). Idempotente: una vez migradas, ninguna tiene el
    canal, así que re-correr no cambia nada.

    Se hace en Python (no en SQL) porque `channels` es JSON y filtrar/editar
    listas JSON es dependiente del dialecto (SQLite vs Postgres)."""
    from agenda_models import Activity

    db = SessionLocal()
    try:
        rows = db.query(Activity).all()
        changed = 0
        for r in rows:
            ch = r.channels if isinstance(r.channels, list) else []
            if "Agenda Compromisos" in ch:
                r.origen = "secretaria"
                # Reasignamos una lista nueva para que SQLAlchemy marque el
                # campo como modificado (mutar in-place no lo detecta en JSON).
                r.channels = [c for c in ch if c != "Agenda Compromisos"]
                changed += 1
        if changed:
            db.commit()
        print(f"Backfill origen: {changed} actividad(es) marcadas como Secretaría.")
    except Exception as e:
        print(f"Error en backfill de origen: {e}")
        db.rollback()
    finally:
        db.close()


def seed_efemerides_if_empty():
    """Inserta el listado inicial de efemérides si la tabla está vacía."""
    from agenda_models import Efemeride
    from seed_efemerides import EFEMERIDES_DATA

    db = SessionLocal()
    try:
        count = db.query(Efemeride).count()
        if count == 0:
            for entry in EFEMERIDES_DATA:
                db.add(Efemeride(**entry))
            db.commit()
            print(f"Seed de efemérides: {len(EFEMERIDES_DATA)} entradas insertadas.")
        else:
            print(f"Seed de efemérides saltado (ya hay {count} entradas).")
    except Exception as e:
        print(f"Error al sembrar efemérides: {e}")
        db.rollback()
    finally:
        db.close()


def seed_metricas_if_empty():
    """Siembra programas + instancias de Métricas FBCR si las tablas están vacías.
    Idempotente: una vez sembrado, las altas se cargan desde el admin."""
    from metricas.models import Instancia, Programa
    from metricas.seed_data import INSTANCIAS, PROGRAMAS

    db = SessionLocal()
    try:
        if db.query(Programa).count() > 0:
            print("Seed de métricas saltado (ya hay programas cargados).")
            return

        slug_to_id = {}
        for p in PROGRAMAS:
            prog = Programa(**p)
            db.add(prog)
            db.flush()  # para tener el id antes del commit
            slug_to_id[prog.slug] = prog.id

        for row in INSTANCIAS:
            data = dict(row)
            slug = data.pop("programa")
            db.add(Instancia(programa_id=slug_to_id[slug], **data))

        db.commit()
        print(f"Seed de métricas: {len(PROGRAMAS)} programas y {len(INSTANCIAS)} instancias insertadas.")
    except Exception as e:
        print(f"Error al sembrar métricas: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

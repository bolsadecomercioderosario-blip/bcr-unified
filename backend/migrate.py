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

    seed_efemerides_if_empty()


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


if __name__ == "__main__":
    migrate()

from sqlalchemy import text
from database import engine

def migrate():
    print("Iniciando migración de base de datos...")
    with engine.connect() as conn:
        # SQLite y Postgres tienen sintaxis similar para esto
        try:
            # Intentamos agregar la columna image_url
            conn.execute(text("ALTER TABLE activities ADD COLUMN image_url VARCHAR DEFAULT ''"))
            conn.commit()
            print("Columna 'image_url' agregada con éxito.")
        except Exception as e:
            # Si falla es porque probablemente ya existe
            print(f"Nota: La migración de 'image_url' se saltó (posiblemente ya existe).")

        try:
            # Por las dudas, chequeamos otras columnas que agregamos recientemente
            conn.execute(text("ALTER TABLE activities ADD COLUMN order_index INTEGER DEFAULT 0"))
            conn.commit()
            print("Columna 'order_index' agregada con éxito.")
        except:
            pass

if __name__ == "__main__":
    migrate()

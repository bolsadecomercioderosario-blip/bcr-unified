"""
Scheduler in-process del bot BCR (APScheduler).

Asumimos un único worker — el plan Starter de Render no se duerme y corre
con 1 worker, así que esta forma es la más simple y barata. Si en el futuro
escalamos a múltiples workers, conviene mover los crons a Render Cron Jobs
separados (un servicio por scraper) en vez de meter locking distribuido acá.

Trigger horario: hora local Argentina (UTC-3).

Cómo registrar un job nuevo:
1. Importar la función pura (que recibe db: Session).
2. Envolverla en un wrapper que abra una Session fresh (no se pueden
   compartir sesiones entre threads/jobs).
3. Llamar scheduler.add_job(wrapper, CronTrigger(...), id="...",
   replace_existing=True).
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal


_TZ = "America/Argentina/Buenos_Aires"

scheduler = BackgroundScheduler(timezone=_TZ)


def _run_scrape_precios_pizarra() -> None:
    """Wrapper para el job diario de precios. Abre Session fresh, corre el
    scraper, loguea el resultado, cierra Session."""
    # Import local para evitar cargar scraper_pizarra (y por ende beautifulsoup)
    # antes de tiempo si el bot no se usa.
    from bot.scraper_pizarra import scrape_precios_pizarra

    db = SessionLocal()
    try:
        result = scrape_precios_pizarra(db)
        print(f"[bot.scheduler] scrape_precios_pizarra → {result}")
    except Exception as exc:  # noqa: BLE001 — no queremos que un fallo mate el scheduler
        print(f"[bot.scheduler] scrape_precios_pizarra falló: {type(exc).__name__}: {exc}")
    finally:
        db.close()


def start() -> None:
    """Arranca el scheduler con los jobs registrados. Idempotente — si ya
    está corriendo (ej. uvicorn --reload), no hace nada."""
    if scheduler.running:
        return

    # Precios pizarra: todos los días a las 10:30 ART. El sitio actualiza a
    # las 10:00, dejamos margen para que esté disponible.
    scheduler.add_job(
        _run_scrape_precios_pizarra,
        CronTrigger(hour=10, minute=30),
        id="scrape_precios_pizarra",
        replace_existing=True,
        max_instances=1,  # No dejar arrancar otro tick si el anterior aún corre
        coalesce=True,    # Si nos perdimos ticks (por restart), correr UNO solo
    )

    scheduler.start()
    print(f"[bot.scheduler] arrancado en TZ={_TZ}. Jobs:")
    for job in scheduler.get_jobs():
        print(f"  - {job.id}: next run = {job.next_run_time}")

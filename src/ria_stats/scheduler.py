"""Runs an update on schedule inside the API process (see api.py).

Collection state lives in the DB, so a wake-up with nothing to do is cheap and a restart loses
nothing. A wake-up takes the update lock and is skipped when a manual update holds it.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ria_stats import settings
from ria_stats.db import SessionLocal
from ria_stats.locking import UpdateInProgress
from ria_stats.update import run_update

JOB_ID = "collection"

log = logging.getLogger("ria_stats.scheduler")


def run_collection() -> None:
    try:
        result = run_update("scheduled")
    except UpdateInProgress:
        log.info("another update is running, skipping this wake-up")
        return
    except Exception:
        log.exception("wake-up failed")
        return

    for d in result.discoveries:
        log.info("discovery %s: %s, %s ids, %s requests", d.id, d.status, d.ids_returned, d.requests_used)
        if d.errors:
            log.warning(d.errors)
    if any(d.status == "rate_limited" for d in result.discoveries):
        log.warning("rate limited, skipping detail collection until the next wake-up")
    elif result.collection is None:
        log.info("no details to collect")
    else:
        run = result.collection
        log.info("run %s: %s, %s requests", run.id, run.status, run.requests_used)
        if run.errors:
            log.warning(run.errors)


def apply_settings(scheduler: BackgroundScheduler) -> None:
    """Make the job follow the settings: its hours (container local time, see TZ in
    docker-compose.yml), and paused when the scheduled sync is switched off."""
    with SessionLocal() as session:
        current = settings.load(session)
    hours = ",".join(str(h) for h in current.run_hours)
    scheduler.reschedule_job(JOB_ID, trigger=CronTrigger(hour=hours, minute=0))
    if current.scheduler_enabled:
        scheduler.resume_job(JOB_ID)
    else:
        scheduler.pause_job(JOB_ID)
    log.info("scheduled sync %s, runs at minute 0 of hours %s", "on" if current.scheduler_enabled else "off", hours)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_collection, CronTrigger(minute=0), id=JOB_ID)
    apply_settings(scheduler)
    scheduler.start()
    return scheduler

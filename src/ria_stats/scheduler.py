"""Long-running process: wakes up on schedule, runs discovery if it is due, then collects details.

Both steps share one client, so the request cap (MAX_REQUESTS) covers them together. State lives
in the DB, so a wake-up with nothing to do is cheap and a restart loses nothing. The container
starts this module (see Dockerfile).

Usage: uv run python -m ria_stats.scheduler
"""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from ria_stats.client import RiaClient
from ria_stats.collector import collect
from ria_stats.db import SessionLocal
from ria_stats.discovery import discover

# Hours of the day (container local time, see TZ in docker-compose.yml) when a run may start.
RUN_HOURS = "12-14"

log = logging.getLogger("ria_stats.scheduler")


def run_collection() -> None:
    try:
        client = RiaClient()
        try:
            with SessionLocal() as session:
                discoveries = discover(session, client)
            for d in discoveries:
                log.info("discovery %s: %s, %s ids, %s requests", d.id, d.status, d.ids_returned, d.requests_used)
                if d.errors:
                    log.warning(d.errors)
            if any(d.status == "rate_limited" for d in discoveries):
                log.warning("rate limited, skipping detail collection until the next wake-up")
                return

            run = collect(client=client)
            if run is None:
                log.info("no details to collect")
            else:
                log.info("run %s: %s, %s requests", run.id, run.status, run.requests_used)
                if run.errors:
                    log.warning(run.errors)
        finally:
            client.close()
    except Exception:
        log.exception("wake-up failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scheduler = BlockingScheduler()
    scheduler.add_job(run_collection, CronTrigger(hour=RUN_HOURS, minute=0))
    log.info("scheduler started, runs at minute 0 of hours %s", RUN_HOURS)
    scheduler.start()

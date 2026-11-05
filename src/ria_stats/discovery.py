"""Discovery: the search sweep that lists every active listing of a tracked model.

A sweep makes search requests only, never /auto/info. It stores a stub listing for every new id
and stamps last_in_search_at on every id found; the details are fetched later by the collector.
Each sweep is logged in discovery_runs, and the latest completed one anchors the model's refresh
cycle. A model is swept again once that run is `refresh_days` (a setting) calendar days old.

Usage: uv run python -m ria_stats.discovery
"""
import argparse
import logging
import sys
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ria_stats.client import ApiError, RateLimited, RiaClient, redact
from ria_stats.config import TRACKED, utcnow
from ria_stats.db import SessionLocal
from ria_stats.locking import UpdateInProgress, update_lock
from ria_stats.logging_setup import setup_logging
from ria_stats.models import DiscoveryRun, Listing, Model
from ria_stats.settings import load as load_settings

log = logging.getLogger("ria_stats.discovery")


def _search_ids(client: RiaClient, brand_ria_id: int, model_ria_id: int) -> tuple[int, list[int]]:
    """Return (total count reported by the API, all listing ids across pages)."""
    ids: list[int] = []
    page = 0
    while True:
        response = client.search(brand_ria_id, model_ria_id, page)
        if response.status_code != 200:  # not raise_for_status(): its message holds the URL, and the key
            raise ApiError(f"search page {page}: HTTP {response.status_code}")
        result = response.json()["result"]["search_result"]
        ids += [int(i) for i in result["ids"]]
        if not result["ids"] or len(ids) >= result["count"]:
            return result["count"], ids
        page += 1


def _is_due(session: Session, model: Model, now: datetime, refresh_days: int) -> bool:
    last = session.scalar(
        select(DiscoveryRun.started_at)
        .where(DiscoveryRun.model_id == model.id, DiscoveryRun.status == "completed")
        .order_by(DiscoveryRun.id.desc())
        .limit(1)
    )
    return last is None or (now.date() - last.date()).days >= refresh_days


def _store(session: Session, model: Model, ids: list[int], started_at: datetime) -> int:
    """Store the sweep's ids; return how many listings were new."""
    known = {
        listing.ria_auto_id: listing
        for listing in session.scalars(select(Listing).where(Listing.ria_auto_id.in_(ids)))
    }
    new = 0
    for auto_id in ids:
        if auto_id in known:
            known[auto_id].last_in_search_at = started_at
        else:
            session.add(Listing(ria_auto_id=auto_id, model=model, first_seen_at=started_at,
                                last_seen_at=started_at, last_in_search_at=started_at))
            new += 1
    return new


def discover(session: Session, client: RiaClient, trigger: str = "manual",
             force: bool = False) -> list[DiscoveryRun]:
    """Sweep every tracked model that is due (all of them with force); return the runs made.

    A completed sweep starts a new refresh cycle, so every listing becomes pending again.
    The caller holds the update lock.
    """
    runs = []
    refresh_days = load_settings(session).refresh_days
    for brand_ria_id, model_ria_id in TRACKED:
        model = session.scalars(select(Model).where(Model.ria_id == model_ria_id)).one()
        now = utcnow()
        if not force and not _is_due(session, model, now, refresh_days):
            continue

        run = DiscoveryRun(model=model, started_at=now, status="running", trigger=trigger)
        session.add(run)
        session.commit()
        requests_before = client.requests_used
        log.info("discovery %s: searching %s %s", run.id, model.brand.name, model.name)
        try:
            run.search_total, ids = _search_ids(client, brand_ria_id, model_ria_id)
            run.ids_returned = len(ids)
            new = _store(session, model, ids, now)
            run.status = "completed"
            log.info("discovery %s: %s listings in search (API total %s), %s new",
                     run.id, len(ids), run.search_total, new)
        except RateLimited as e:
            run.status = "rate_limited"
            run.errors = f"HTTP 429 on {e}"
        except (httpx.HTTPError, ApiError) as e:
            session.rollback()
            run.status = "failed"
            run.errors = redact(repr(e))
        except Exception as e:
            session.rollback()
            run.status = "failed"
            run.errors = redact(repr(e))
            raise
        finally:
            run.requests_used = client.requests_used - requests_before
            run.finished_at = utcnow()
            session.commit()
            session.refresh(run)  # keep attributes loaded for the caller
        runs.append(run)
        if run.status == "rate_limited":
            break
    return runs


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="sweep even if one completed recently")
    force = parser.parse_args().force
    try:
        with update_lock():
            client = RiaClient()
            try:
                with SessionLocal() as session:
                    runs = discover(session, client, force=force)
            finally:
                client.close()
    except UpdateInProgress as e:
        sys.exit(str(e))
    for run in runs:
        print(f"discovery {run.id} (model {run.model_id}): {run.status}, {run.ids_returned} ids, "
              f"{run.requests_used} requests")
        if run.errors:
            print(run.errors)
    if not runs:
        print("no discovery due")

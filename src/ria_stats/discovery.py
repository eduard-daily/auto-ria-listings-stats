"""Discovery: the search sweep that lists every active listing of a tracked model.

A sweep makes search requests only, never /auto/info. It stores a stub listing for every new id
and stamps last_in_search_at on every id found; the details are fetched later by the collector.
Each sweep is logged in discovery_runs, and the latest completed one anchors the model's refresh
cycle. A model is swept again once that run is REFRESH_DAYS calendar days old.

Usage: uv run python -m ria_stats.discovery
"""
import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ria_stats.client import RateLimited, RiaClient
from ria_stats.config import REFRESH_DAYS, TRACKED, utcnow
from ria_stats.db import SessionLocal
from ria_stats.models import DiscoveryRun, Listing, Model

log = logging.getLogger("ria_stats.discovery")


def _search_ids(client: RiaClient, brand_ria_id: int, model_ria_id: int) -> tuple[int, list[int]]:
    """Return (total count reported by the API, all listing ids across pages)."""
    ids: list[int] = []
    page = 0
    while True:
        response = client.search(brand_ria_id, model_ria_id, page)
        response.raise_for_status()
        result = response.json()["result"]["search_result"]
        ids += [int(i) for i in result["ids"]]
        if not result["ids"] or len(ids) >= result["count"]:
            return result["count"], ids
        page += 1


def _is_due(session: Session, model: Model, now: datetime) -> bool:
    last = session.scalar(
        select(DiscoveryRun.started_at)
        .where(DiscoveryRun.model_id == model.id, DiscoveryRun.status == "completed")
        .order_by(DiscoveryRun.id.desc())
        .limit(1)
    )
    return last is None or (now.date() - last.date()).days >= REFRESH_DAYS


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


def discover(session: Session, client: RiaClient) -> list[DiscoveryRun]:
    """Sweep every tracked model that is due; return the runs made (none when nothing is due)."""
    runs = []
    for brand_ria_id, model_ria_id in TRACKED:
        model = session.scalars(select(Model).where(Model.ria_id == model_ria_id)).one()
        now = utcnow()
        if not _is_due(session, model, now):
            continue

        run = DiscoveryRun(model=model, started_at=now, status="running")
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
        except httpx.HTTPError as e:
            session.rollback()
            run.status = "failed"
            run.errors = repr(e)
        except Exception as e:
            session.rollback()
            run.status = "failed"
            run.errors = repr(e)
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = RiaClient()
    try:
        with SessionLocal() as session:
            runs = discover(session, client)
    finally:
        client.close()
    for run in runs:
        print(f"discovery {run.id} (model {run.model_id}): {run.status}, {run.ids_returned} ids, "
              f"{run.requests_used} requests")
        if run.errors:
            print(run.errors)
    if not runs:
        print("no discovery due")

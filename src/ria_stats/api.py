"""JSON API for the frontend, with the scheduler running inside the same process.

Run with a single worker (the scheduler lives in this process):
uvicorn ria_stats.api:app --host 0.0.0.0 --port 8000
"""
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from ria_stats.collector import pending_count
from ria_stats.db import SessionLocal
from ria_stats.locking import UpdateInProgress, update_running
from ria_stats.logging_setup import setup_logging
from ria_stats.models import CollectionRun, DiscoveryRun, Listing, ListingSnapshot
from ria_stats.scheduler import start_scheduler
from ria_stats.schemas import (CollectionRunOut, DiscoveryRunOut, ListingDetail, ListingRow, ModelOption,
                               Snapshot, Stats, UpdateOut)
from ria_stats.update import UpdateResult, refresh_listing, run_update

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="ria-stats", lifespan=lifespan)

STATUSES = ("pending", "active", "sold", "removed")


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def _discovery_out(run: DiscoveryRun) -> DiscoveryRunOut:
    return DiscoveryRunOut(
        id=run.id, model=run.model.name, started_at=run.started_at, finished_at=run.finished_at,
        status=run.status, trigger=run.trigger, requests_used=run.requests_used,
        search_total=run.search_total, ids_returned=run.ids_returned, errors=run.errors,
    )


def _collection_out(run: CollectionRun) -> CollectionRunOut:
    return CollectionRunOut.model_validate(run, from_attributes=True)


def _update_out(result: UpdateResult) -> UpdateOut:
    return UpdateOut(
        discoveries=[_discovery_out(d) for d in result.discoveries],
        collection=_collection_out(result.collection) if result.collection else None,
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/models")
def models(session: Session = Depends(get_session)) -> list[ModelOption]:
    rows = session.execute(text(
        "SELECT brand_id, brand, model_id, model, COUNT(*) AS listings FROM listing_latest "
        "GROUP BY brand_id, brand, model_id, model ORDER BY brand, model"
    )).mappings()
    return [ModelOption(**row) for row in rows]


@app.get("/api/listings")
def listings(model_id: int | None = None, status: list[str] = Query(default=list(STATUSES)),
             session: Session = Depends(get_session)) -> list[ListingRow]:
    if unknown := set(status) - set(STATUSES):
        raise HTTPException(422, f"unknown status: {', '.join(sorted(unknown))}")
    query = "SELECT * FROM listing_latest WHERE status IN :statuses"
    params: dict = {"statuses": status}
    if model_id is not None:
        query += " AND model_id = :model_id"
        params["model_id"] = model_id
    rows = session.execute(text(query).bindparams(bindparam("statuses", expanding=True)), params).mappings()
    return [ListingRow(**row) for row in rows]


@app.get("/api/listings/{auto_id}")
def listing(auto_id: int, session: Session = Depends(get_session)) -> ListingDetail:
    row = session.execute(text("SELECT * FROM listing_latest WHERE ria_auto_id = :id"), {"id": auto_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "unknown listing")
    entity = session.scalars(select(Listing).where(Listing.ria_auto_id == auto_id)).one()
    snapshots = session.execute(text(
        "SELECT s.*, p.listed_currency, p.listed_price FROM listing_snapshots s "
        "LEFT JOIN snapshot_prices p ON p.snapshot_id = s.id WHERE s.listing_id = :id ORDER BY s.id"
    ), {"id": entity.id}).mappings()
    return ListingDetail(
        **row,
        **{field: getattr(entity, field) for field in (
            "plate", "generation", "modification", "equipment", "body_type", "fuel_label", "gearbox",
            "drive", "color", "description", "seller_ria_id", "dealer_type", "dealer_name", "last_in_search_at")},
        snapshots=[Snapshot(**s) for s in snapshots],
    )


@app.get("/api/stats")
def stats(session: Session = Depends(get_session)) -> Stats:
    by_status = dict(session.execute(text("SELECT status, COUNT(*) FROM listing_latest GROUP BY status")).all())
    discovery_runs = session.scalars(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(50))
    collection_runs = session.scalars(select(CollectionRun).order_by(CollectionRun.id.desc()).limit(50))
    return Stats(
        update_running=update_running(),
        pending_fetch=pending_count(session),
        listings_by_status={status: by_status.get(status, 0) for status in STATUSES},
        snapshots=session.scalar(select(func.count()).select_from(ListingSnapshot)),
        requests_total=(session.scalar(select(func.coalesce(func.sum(DiscoveryRun.requests_used), 0)))
                        + session.scalar(select(func.coalesce(func.sum(CollectionRun.requests_used), 0)))),
        discovery_runs=[_discovery_out(r) for r in discovery_runs],
        collection_runs=[_collection_out(r) for r in collection_runs],
    )


@app.post("/api/update")
def update() -> UpdateOut:
    """The scheduler's wake-up, on demand: discovery if due, then detail collection."""
    try:
        return _update_out(run_update("manual"))
    except UpdateInProgress as e:
        raise HTTPException(409, str(e)) from None


@app.post("/api/discovery/force")
def force_discovery() -> UpdateOut:
    """Discovery now, even if not due. Starts a new cycle: every listing becomes pending again."""
    try:
        return _update_out(run_update("manual", force=True))
    except UpdateInProgress as e:
        raise HTTPException(409, str(e)) from None


@app.post("/api/listings/{auto_id}/refresh")
def refresh(auto_id: int) -> CollectionRunOut:
    try:
        return _collection_out(refresh_listing(auto_id))
    except UpdateInProgress as e:
        raise HTTPException(409, str(e)) from None
    except LookupError:
        raise HTTPException(404, "unknown listing") from None

"""JSON API for the frontend, with the scheduler running inside the same process.

Run with a single worker (the scheduler lives in this process):
uvicorn ria_stats.api:app --host 0.0.0.0 --port 8000
"""
import re
from collections.abc import Iterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from ria_stats import photo_store, settings
from ria_stats.collector import pending_count
from ria_stats.db import SessionLocal
from ria_stats.locking import UpdateInProgress, update_running
from ria_stats.logging_setup import setup_logging
from ria_stats.models import CollectionRun, DiscoveryRun, Listing, ListingPhoto, ListingSnapshot
from ria_stats.scheduler import apply_settings, start_scheduler
from ria_stats.schemas import (CollectionRunOut, DiscoveryRunOut, ListingDetail, ListingRow, ModelOption,
                               PhotoOut, PhotosOut, SettingsOut, Snapshot, Stats, UpdateOut)
from ria_stats.update import UpdateResult, refresh_listing, run_update


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    scheduler = app.state.scheduler = start_scheduler()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="ria-stats", lifespan=lifespan)


@app.middleware("http")
async def refuse_cross_origin_writes(request: Request, call_next):
    """There is no login, so a page on another site must not be able to start an update.

    Browsers attach an Origin header to cross-origin writes; it has to name this very host.
    Requests without one (curl, scripts) are not browser-driven and pass.
    """
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin is not None:
        if urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
    return await call_next(request)

STATUSES = ("pending", "active", "sold", "removed")
PHOTO_STATUSES = ("pending", "ok", "gone", "failed")
PHOTO_FILE = re.compile(r"^\d+\.jpg$")


def _photo_url(auto_id: int, photo_id: int) -> str:
    return f"/api/photos/{auto_id}/{photo_id}.jpg"


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
        photos=PhotosOut(downloaded=result.photos.downloaded, gone=result.photos.gone,
                         failed=result.photos.failed, remaining=result.photos.remaining),
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
    query = ("SELECT ll.*, l.gearbox, "
             "(SELECT p.ria_photo_id FROM listing_photos p WHERE p.listing_id = ll.listing_id AND p.status = 'ok' "
             " ORDER BY p.is_cover DESC, p.position LIMIT 1) AS cover_photo_id "
             "FROM listing_latest ll JOIN listings l ON l.id = ll.listing_id WHERE ll.status IN :statuses")
    params: dict = {"statuses": status}
    if model_id is not None:
        query += " AND ll.model_id = :model_id"
        params["model_id"] = model_id
    rows = session.execute(text(query).bindparams(bindparam("statuses", expanding=True)), params).mappings()
    return [
        ListingRow(**row, cover_photo=_photo_url(row["ria_auto_id"], row["cover_photo_id"]) if row["cover_photo_id"] else None)
        for row in rows
    ]


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
    photos = session.scalars(
        select(ListingPhoto)
        .where(ListingPhoto.listing_id == entity.id, ListingPhoto.status == "ok")
        .order_by(ListingPhoto.is_cover.desc(), ListingPhoto.position)
    ).all()
    photo_list = [PhotoOut(id=p.ria_photo_id, url=_photo_url(auto_id, p.ria_photo_id), is_cover=p.is_cover,
                           position=p.position) for p in photos]
    return ListingDetail(
        **row,
        cover_photo=photo_list[0].url if photo_list else None,
        photos=photo_list,
        **{field: getattr(entity, field) for field in (
            "plate", "generation", "modification", "equipment", "body_type", "fuel_label", "gearbox",
            "drive", "color", "description", "seller_ria_id", "dealer_type", "dealer_name", "last_in_search_at")},
        snapshots=[Snapshot(**s) for s in snapshots],
    )


@app.get("/api/stats")
def stats(session: Session = Depends(get_session)) -> Stats:
    by_status = dict(session.execute(text("SELECT status, COUNT(*) FROM listing_latest GROUP BY status")).all())
    photo_counts = dict(session.execute(select(ListingPhoto.status, func.count()).group_by(ListingPhoto.status)).all())
    discovery_runs = session.scalars(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(50))
    collection_runs = session.scalars(select(CollectionRun).order_by(CollectionRun.id.desc()).limit(50))
    return Stats(
        update_running=update_running(),
        pending_fetch=pending_count(session),
        listings_by_status={status: by_status.get(status, 0) for status in STATUSES},
        photos={status: photo_counts.get(status, 0) for status in PHOTO_STATUSES},
        snapshots=session.scalar(select(func.count()).select_from(ListingSnapshot)),
        requests_total=(session.scalar(select(func.coalesce(func.sum(DiscoveryRun.requests_used), 0)))
                        + session.scalar(select(func.coalesce(func.sum(CollectionRun.requests_used), 0)))),
        discovery_runs=[_discovery_out(r) for r in discovery_runs],
        collection_runs=[_collection_out(r) for r in collection_runs],
    )


def _settings_out(session: Session) -> SettingsOut:
    return SettingsOut(values=settings.load(session), defaults=settings.Settings(), limits=settings.LIMITS)


@app.get("/api/settings")
def get_settings(session: Session = Depends(get_session)) -> SettingsOut:
    return _settings_out(session)


@app.put("/api/settings")
def put_settings(new: settings.Settings, session: Session = Depends(get_session)) -> SettingsOut:
    """Replace all settings. The scheduler follows at once; everything else on its next run."""
    settings.save(session, new)
    session.commit()
    if scheduler := getattr(app.state, "scheduler", None):  # absent when the lifespan did not run (tests)
        apply_settings(scheduler)
    return _settings_out(session)


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


@app.get("/api/photos/{auto_id}/{photo_file}")
def photo(auto_id: int, photo_file: str) -> FileResponse:
    if not PHOTO_FILE.match(photo_file):
        raise HTTPException(404, "unknown photo")
    path = photo_store.path(f"{auto_id}/{photo_file}")
    if not path.is_file():
        raise HTTPException(404, "unknown photo")
    # A photo's file name contains its own id and the file never changes.
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})

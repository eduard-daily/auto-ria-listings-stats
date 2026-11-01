"""Detail collection: /auto/info calls for listings found by discovery, capped per run.

Never searches. For each model, the start of its latest completed discovery anchors the refresh
cycle. A run fetches what has no snapshot since that anchor: listings still in search, plus
listings that left search while their last snapshot said "in search" (one final fetch). A run
with nothing to do writes nothing, so a cycle takes as many runs as the request cap requires.

Requests are sent back to back. On HTTP 429 the run stops and is marked "rate_limited";
work saved before that is kept and the next run continues.

Usage: uv run python -m ria_stats.collector [--max-requests N]
"""
import argparse
import logging
from datetime import datetime

import httpx
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from ria_stats.client import RateLimited, RiaClient
from ria_stats.config import MAX_REQUESTS, utcnow
from ria_stats.db import SessionLocal
from ria_stats.models import CollectionRun, DiscoveryRun, Listing, ListingSnapshot, Location

SITE_URL = "https://auto.ria.com"

log = logging.getLogger("ria_stats.collector")


def _api_date(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _location(session: Session, state: dict) -> Location | None:
    if not state.get("stateId"):
        return None
    location = session.scalar(select(Location).where(Location.ria_state_id == state["stateId"]))
    if location is None:
        location = Location(
            ria_state_id=state["stateId"],
            city_name=state["name"],
            region_name=state.get("regionName"),
            region_name_eng=state.get("regionNameEng"),
        )
        session.add(location)
    return location


def _apply_info(session: Session, listing: Listing, data: dict, now: datetime) -> None:
    auto = data.get("autoData", {})
    dealer = data.get("dealer", {})
    fuel_label = auto.get("fuelName")

    listing.location = _location(session, data.get("stateData", {}))
    listing.link = SITE_URL + data["linkToView"] if data.get("linkToView") else None
    listing.title = data.get("title")
    listing.year = auto.get("year")
    listing.generation = auto.get("generationName")
    listing.modification = auto.get("modificationName")
    listing.equipment = auto.get("equipmentName")
    listing.body_type = data.get("subCategoryName")
    listing.fuel_type = fuel_label.split(",")[0] if fuel_label else None
    listing.fuel_label = fuel_label
    listing.gearbox = auto.get("gearboxName")
    listing.drive = auto.get("driveName")
    listing.color = data.get("color", {}).get("name")
    listing.vin = data.get("VIN") or None
    listing.plate = data.get("plateNumber") or data.get("plateNumberData", {}).get("text") or None
    listing.description = auto.get("description")
    listing.seller_ria_id = data.get("userId")
    listing.dealer_type = dealer.get("type") or None
    listing.dealer_name = dealer.get("name") or None
    listing.posted_at = _api_date(data.get("addDate"))
    listing.last_seen_at = now


def _snapshot(listing: Listing, run: CollectionRun, now: datetime, in_search: bool,
              response: httpx.Response | None) -> ListingSnapshot:
    snapshot = ListingSnapshot(
        listing=listing,
        run=run,
        observed_at=now,
        in_search=in_search,
        fetch_ok=response is not None and response.status_code == 200,
        http_status=response.status_code if response is not None else None,
    )
    if snapshot.fetch_ok:
        data = response.json()
        auto = data.get("autoData", {})
        snapshot.price_usd = data.get("USD")
        snapshot.price_eur = data.get("EUR")
        snapshot.price_uah = data.get("UAH")
        snapshot.main_currency = auto.get("mainCurrency")
        snapshot.mileage_k_km = auto.get("raceInt")
        snapshot.update_date = _api_date(data.get("updateDate"))
        snapshot.expire_date = _api_date(data.get("expireDate"))
        snapshot.sold_date = _api_date(data.get("soldDate"))
        snapshot.active = auto.get("active")
        snapshot.is_sold = auto.get("isSold")
        snapshot.from_archive = auto.get("fromArchive")
        snapshot.on_moderation = auto.get("onModeration")
        snapshot.status_id = auto.get("statusId")
        snapshot.status_id5_type = data.get("statusId5Type")
    return snapshot


def _fetch_info(client: RiaClient, auto_id: int, errors: list[str]) -> httpx.Response | None:
    """None means the request itself failed (timeout, connection error)."""
    try:
        response = client.info(auto_id)
    except httpx.HTTPError as e:
        errors.append(f"info {auto_id}: {e!r}")
        return None
    if response.status_code != 200:
        errors.append(f"info {auto_id}: HTTP {response.status_code}")
    return response


def _anchors(session: Session) -> dict[int, datetime]:
    """Model id -> start of its latest completed discovery."""
    rows = session.execute(
        select(DiscoveryRun.model_id, func.max(DiscoveryRun.started_at))
        .where(DiscoveryRun.status == "completed")
        .group_by(DiscoveryRun.model_id)
    )
    return dict(rows.all())


def _pending(session: Session) -> list[tuple[Listing, datetime]]:
    """Listings that still need a fetch, each with the anchor of its model's cycle."""
    pending = []
    for model_id, anchor in _anchors(session).items():
        fresh = exists().where(ListingSnapshot.listing_id == Listing.id, ListingSnapshot.observed_at >= anchor)
        latest_in_search = (
            select(ListingSnapshot.in_search)
            .where(ListingSnapshot.listing_id == Listing.id)
            .order_by(ListingSnapshot.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        in_search_now = Listing.last_in_search_at >= anchor
        departed = (Listing.last_in_search_at < anchor) & latest_in_search.is_(True)
        listings = session.scalars(
            select(Listing).where(Listing.model_id == model_id, ~fresh, in_search_now | departed).order_by(Listing.id)
        )
        pending += [(listing, anchor) for listing in listings]
    return pending


def _fetch_pending(session: Session, client: RiaClient, run: CollectionRun, max_requests: int,
                   errors: list[str]) -> None:
    pending = _pending(session)
    log.info("%s listings to fetch, request budget %s", len(pending), max_requests - client.requests_used)
    for n, (listing, anchor) in enumerate(pending, 1):
        if client.requests_used >= max_requests:
            log.info("request cap reached, %s listings left for the next run", len(pending) - n + 1)
            break
        now = utcnow()
        in_search = listing.last_in_search_at >= anchor
        response = _fetch_info(client, listing.ria_auto_id, errors)
        if response is not None and response.status_code == 200:
            _apply_info(session, listing, response.json(), now)
        snapshot = _snapshot(listing, run, now, in_search=in_search, response=response)
        session.add(snapshot)
        session.commit()
        outcome = (f"${snapshot.price_usd}, {snapshot.mileage_k_km}k km" if snapshot.fetch_ok
                   else f"fetch failed, HTTP {snapshot.http_status}")
        log.info("[%s/%s] listing %s (%s %s): %s%s", n, len(pending), listing.ria_auto_id, listing.title,
                 listing.year, outcome, "" if in_search else ", left search")


def collect(max_requests: int = MAX_REQUESTS, client: RiaClient | None = None) -> CollectionRun | None:
    """Run one slice of detail collection; None when there is nothing to do.

    Pass a client to share its request counter (and so the cap) with earlier work.
    """
    with SessionLocal() as session:
        if not _pending(session):
            return None

        own_client = client is None
        client = client or RiaClient()
        requests_before = client.requests_used
        errors: list[str] = []
        run = CollectionRun(started_at=utcnow(), status="running")
        session.add(run)
        session.commit()
        try:
            _fetch_pending(session, client, run, max_requests, errors)
            run.status = "completed_with_errors" if errors else "completed"
        except RateLimited as e:
            errors.append(f"HTTP 429 on {e}")
            run.status = "rate_limited"
        except Exception as e:
            session.rollback()
            errors.append(f"aborted: {e!r}")
            run.status = "failed"
            raise
        finally:
            run.finished_at = utcnow()
            run.requests_used = client.requests_used - requests_before
            run.errors = "\n".join(errors) or None
            session.commit()
            session.refresh(run)  # keep attributes loaded for the caller after the session closes
            if own_client:
                client.close()
    return run


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS,
                        help="stop after this many API requests (default: %(default)s)")
    finished = collect(parser.parse_args().max_requests)
    if finished is None:
        print("nothing to do (run ria_stats.discovery first if no discovery has completed yet)")
    else:
        print(f"run {finished.id}: {finished.status}, {finished.requests_used} requests")
        if finished.errors:
            print(finished.errors)

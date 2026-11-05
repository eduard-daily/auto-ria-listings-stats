"""Backfill: add listings that are already gone from AUTO.RIA, from their ids or links.

A gone listing still answers /auto/info with its last state, so one request gives its attributes,
final price and status, and photo ids. That is a single observation, not a price history. Only
tracked models are accepted, and a listing that is still active is refused because discovery
already collects it. Photos are downloaded right away.

Usage: uv run python -m ria_stats.backfill <id or link> [<id or link> ...]
"""
import argparse
import re
import sys
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ria_stats.client import RateLimited, RiaClient, redact
from ria_stats.collector import _apply_info, _snapshot
from ria_stats.config import TRACKED, utcnow
from ria_stats.db import SessionLocal
from ria_stats.locking import UpdateInProgress, update_lock
from ria_stats.logging_setup import setup_logging
from ria_stats.models import CollectionRun, Listing, Model
from ria_stats.photos import PhotoResult, download_pending, sync_photos
from ria_stats.settings import load as load_settings


@dataclass
class Outcome:
    auto_id: int
    status: str  # added, exists, active, not_tracked, not_found, failed, rate_limited or skipped
    message: str
    listing_id: int | None = None
    photos: PhotoResult | None = None


def parse_auto_id(text: str) -> int:
    """A plain id, or an AUTO.RIA link such as .../auto_mazda_mx_5_39932487.html?utm_source=..."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    match = re.search(r"_(\d+)\.html", text)
    if match:
        return int(match.group(1))
    raise ValueError(f"not a listing id or an AUTO.RIA listing link: {text!r}")


def _backfill_one(session: Session, client: RiaClient, run: CollectionRun, auto_id: int) -> Outcome:
    if session.scalar(select(Listing.id).where(Listing.ria_auto_id == auto_id)) is not None:
        return Outcome(auto_id, "exists", "already in the database")
    try:
        response = client.info(auto_id)  # RateLimited is handled by the caller
    except httpx.HTTPError as e:
        return Outcome(auto_id, "failed", redact(f"request failed: {e!r}"))
    if response.status_code != 200:
        return Outcome(auto_id, "not_found", f"AUTO.RIA answered HTTP {response.status_code}: "
                       "the listing is no longer available, or the id is wrong")

    now = utcnow()
    try:
        data = response.json()
        name = f'{data.get("markName")} {data.get("modelName")}'
        if (data.get("markId"), data.get("modelId")) not in TRACKED:
            return Outcome(auto_id, "not_tracked", f"{name} is not a tracked model; only tracked models can be backfilled")
        if data["autoData"].get("active"):
            return Outcome(auto_id, "active", f"still active on AUTO.RIA. {name} is a tracked car, so the normal "
                           "discovery already collects it; there is nothing to backfill")

        model = session.scalars(select(Model).where(Model.ria_id == data["modelId"])).one()
        listing = Listing(ria_auto_id=auto_id, model_id=model.id, first_seen_at=now, last_seen_at=now)
        session.add(listing)
        session.flush()
        _apply_info(session, listing, data, now)
        sync_photos(session, listing, data, now)
        snapshot = _snapshot(listing, run, now, in_search=False, response=response)
        session.add(snapshot)
        session.commit()
    except Exception as e:  # a malformed response must not stop the rest of the batch
        session.rollback()
        return Outcome(auto_id, "failed", redact(f"unusable response: {e!r}"))

    price = f"${snapshot.price_usd}" if snapshot.main_currency == "USD" else f"{snapshot.main_currency} price"
    count = (data.get("photoData") or {}).get("count") or 0
    return Outcome(auto_id, "added", f"{listing.title} {listing.year}, last price {price}, {count} photos listed",
                   listing_id=listing.id)


def backfill(auto_ids: list[int], client: RiaClient | None = None, http: httpx.Client | None = None) -> list[Outcome]:
    """Backfill each id in turn, one API request each; the caller holds the update lock."""
    own_client = client is None
    client = client or RiaClient()
    outcomes: list[Outcome] = []
    try:
        with SessionLocal() as session:
            run = CollectionRun(started_at=utcnow(), status="running", trigger="backfill")
            session.add(run)
            session.commit()
            for position, auto_id in enumerate(auto_ids):
                try:
                    outcomes.append(_backfill_one(session, client, run, auto_id))
                except RateLimited:
                    outcomes.append(Outcome(auto_id, "rate_limited", "AUTO.RIA rate limit reached; try again in an hour"))
                    outcomes += [Outcome(rest, "skipped", "not attempted: rate limited") for rest in auto_ids[position + 1:]]
                    break
            problems = [o for o in outcomes if o.status in ("failed", "rate_limited")]
            run.status = ("rate_limited" if any(o.status == "rate_limited" for o in problems)
                          else "completed_with_errors" if problems else "completed")
            run.errors = "\n".join(f"{o.auto_id}: {o.message}" for o in problems) or None
            run.requests_used = client.requests_used
            run.finished_at = utcnow()
            session.commit()
    finally:
        if own_client:
            client.close()

    for outcome in outcomes:
        if outcome.status == "added":
            outcome.photos = download_pending(listing_id=outcome.listing_id, http=http)
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add listings that are already gone from AUTO.RIA.")
    parser.add_argument("listings", nargs="+", metavar="ID_OR_LINK", help="a listing id or an AUTO.RIA listing link")
    args = parser.parse_args(argv)
    try:
        ids = list(dict.fromkeys(parse_auto_id(text) for text in args.listings))
    except ValueError as e:
        parser.error(str(e))
    with SessionLocal() as session:
        max_requests = load_settings(session).max_requests
    if len(ids) > max_requests:
        parser.error(f"at most {max_requests} listings at a time (one API request each; the hourly cap is 30)")

    setup_logging()
    try:
        with update_lock():
            outcomes = backfill(ids)
    except UpdateInProgress as e:
        print(e)
        return 1
    for outcome in outcomes:
        line = f"{outcome.auto_id}: {outcome.status} - {outcome.message}"
        if outcome.photos:
            p = outcome.photos
            line += f"; photos: {p.downloaded} downloaded, {p.gone} gone, {p.failed} failed"
        print(line)
    return 0 if all(o.status in ("added", "exists") for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Response shapes of the JSON API.

Our own timestamps (observed_at, started_at, ...) are stored as naive UTC and sent as UTC.
Dates that come from AUTO.RIA (posted_at, update_date, ...) are stored as received, in site
local time, and are sent without a timezone.
"""
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel

UtcDateTime = Annotated[datetime, AfterValidator(lambda d: d.replace(tzinfo=UTC))]


class ModelOption(BaseModel):
    brand_id: int
    brand: str
    model_id: int
    model: str
    listings: int


class ListingRow(BaseModel):
    ria_auto_id: int
    model_id: int
    brand: str
    model: str
    title: str | None
    year: int | None
    gearbox: str | None
    link: str | None
    city: str | None
    region: str | None
    status: str  # pending | active | sold | removed (provisional rules, see migration 0004)
    currency: str | None
    price: int | None  # in the seller's currency
    price_usd: int | None  # as converted at the last fetch; for sorting across currencies
    first_price: int | None
    price_changes: int
    mileage_k_km: int | None
    posted_at: datetime | None
    first_seen_at: UtcDateTime
    last_observed_at: UtcDateTime | None
    cover_photo: str | None = None  # URL of the downloaded cover photo, if there is one


class Snapshot(BaseModel):
    observed_at: UtcDateTime
    run_id: int
    in_search: bool
    fetch_ok: bool
    http_status: int | None
    listed_currency: str | None
    listed_price: int | None
    price_usd: int | None
    price_eur: int | None
    price_uah: int | None
    mileage_k_km: int | None
    update_date: datetime | None
    expire_date: datetime | None
    sold_date: datetime | None
    active: bool | None
    is_sold: bool | None
    from_archive: bool | None
    on_moderation: bool | None
    status_id: int | None
    status_id5_type: int | None


class PhotoOut(BaseModel):
    id: int
    url: str
    is_cover: bool
    position: int


class ListingDetail(ListingRow):
    vin: str | None
    plate: str | None
    generation: str | None
    modification: str | None
    equipment: str | None
    body_type: str | None
    fuel_label: str | None
    drive: str | None
    color: str | None
    description: str | None
    seller_ria_id: int | None
    dealer_type: str | None
    dealer_name: str | None
    last_in_search_at: UtcDateTime | None
    photos: list[PhotoOut]  # downloaded ones, cover first
    snapshots: list[Snapshot]


class DiscoveryRunOut(BaseModel):
    id: int
    model: str
    started_at: UtcDateTime
    finished_at: UtcDateTime | None
    status: str
    trigger: str
    requests_used: int
    search_total: int | None
    ids_returned: int | None
    errors: str | None


class CollectionRunOut(BaseModel):
    id: int
    started_at: UtcDateTime
    finished_at: UtcDateTime | None
    status: str
    trigger: str
    requests_used: int
    errors: str | None


class Stats(BaseModel):
    update_running: bool
    pending_fetch: int
    listings_by_status: dict[str, int]
    snapshots: int
    requests_total: int
    photos: dict[str, int]  # photo count by status: pending, ok, gone, failed
    discovery_runs: list[DiscoveryRunOut]  # newest first, last 50
    collection_runs: list[CollectionRunOut]


class PhotosOut(BaseModel):
    downloaded: int
    gone: int
    failed: int
    remaining: int


class UpdateOut(BaseModel):
    discoveries: list[DiscoveryRunOut]
    collection: CollectionRunOut | None
    photos: PhotosOut

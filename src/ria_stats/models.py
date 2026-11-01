from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Datetimes from the API (addDate, updateDate, ...) are stored as received, without
# timezone conversion. Our own timestamps (first_seen_at, started_at, ...) are UTC.


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    ria_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str]
    name_eng: Mapped[str]


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    ria_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str]
    name_eng: Mapped[str]

    brand: Mapped[Brand] = relationship()


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ria_state_id: Mapped[int] = mapped_column(unique=True)
    city_name: Mapped[str]
    region_name: Mapped[str | None]
    region_name_eng: Mapped[str | None]


class Listing(Base):
    """One AUTO.RIA advert. Holds the latest known values of its static attributes."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    ria_auto_id: Mapped[int] = mapped_column(unique=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    link: Mapped[str | None]
    title: Mapped[str | None]

    year: Mapped[int | None]
    generation: Mapped[str | None]
    modification: Mapped[str | None]
    equipment: Mapped[str | None]
    body_type: Mapped[str | None]
    fuel_type: Mapped[str | None]
    fuel_label: Mapped[str | None]  # raw, e.g. "Бензин, 2 л."
    gearbox: Mapped[str | None]
    drive: Mapped[str | None]
    color: Mapped[str | None]
    vin: Mapped[str | None]
    plate: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)

    seller_ria_id: Mapped[int | None]
    dealer_type: Mapped[str | None]
    dealer_name: Mapped[str | None]

    posted_at: Mapped[datetime | None]
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    last_in_search_at: Mapped[datetime | None]
    photos_synced_at: Mapped[datetime | None]  # when its photos were recorded; once per listing

    model: Mapped[Model] = relationship()
    location: Mapped[Location | None] = relationship()


class DiscoveryRun(Base):
    """One search sweep for one model: lists every active listing, no detail calls."""

    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    requests_used: Mapped[int] = mapped_column(default=0)
    search_total: Mapped[int | None]
    ids_returned: Mapped[int | None]
    errors: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str]
    trigger: Mapped[str] = mapped_column(server_default="manual")  # "manual" or "scheduled"

    model: Mapped[Model] = relationship(lazy="joined")  # callers read it after the session closes


class CollectionRun(Base):
    """One slice of detail collection: /auto/info calls only."""

    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    requests_used: Mapped[int] = mapped_column(default=0)
    errors: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str]
    trigger: Mapped[str] = mapped_column(server_default="manual")  # "manual" or "scheduled"


class ListingPhoto(Base):
    """One photo of a listing, recorded when the listing is first fetched and downloaded once."""

    __tablename__ = "listing_photos"
    __table_args__ = (UniqueConstraint("listing_id", "ria_photo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    ria_photo_id: Mapped[int]
    url_slug: Mapped[str]  # "{markNameEng}_{modelNameEng}", part of the CDN URL
    position: Mapped[int]  # order in the listing's photo list
    is_cover: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(default="pending")  # pending | ok | gone (404) | failed
    http_status: Mapped[int | None]
    variant: Mapped[str | None]  # CDN size suffix that was downloaded: "hd" or "f"
    key: Mapped[str | None]  # file location relative to the photo store, see photo_store.py
    size_bytes: Mapped[int | None]
    first_seen_at: Mapped[datetime]
    downloaded_at: Mapped[datetime | None]


class ListingSnapshot(Base):
    """One listing in one run. Kept even when nothing changed."""

    __tablename__ = "listing_snapshots"
    __table_args__ = (UniqueConstraint("listing_id", "run_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("collection_runs.id"))
    observed_at: Mapped[datetime]

    price_usd: Mapped[int | None]
    price_eur: Mapped[int | None]
    price_uah: Mapped[int | None]
    main_currency: Mapped[str | None]
    mileage_k_km: Mapped[int | None]

    in_search: Mapped[bool]
    fetch_ok: Mapped[bool]
    http_status: Mapped[int | None]

    update_date: Mapped[datetime | None]
    expire_date: Mapped[datetime | None]
    sold_date: Mapped[datetime | None]

    active: Mapped[bool | None]
    is_sold: Mapped[bool | None]
    from_archive: Mapped[bool | None]
    on_moderation: Mapped[bool | None]
    status_id: Mapped[int | None]
    status_id5_type: Mapped[int | None]

    listing: Mapped[Listing] = relationship()
    run: Mapped[CollectionRun] = relationship()

from datetime import datetime

import httpx
from sqlalchemy import select

from helpers import load_fixture
from ria_stats import collector
from ria_stats.models import CollectionRun, Listing, Model

NOW = datetime(2026, 11, 1, 12, 0)


def parse(db, fixture: str):
    """Run one /auto/info response through the collector's parsing; return (listing, snapshot)."""
    data = load_fixture(fixture)
    with db() as session:
        model = session.scalars(select(Model)).first()
        listing = Listing(ria_auto_id=1, model_id=model.id, first_seen_at=NOW, last_seen_at=NOW)
        run = CollectionRun(started_at=NOW, status="running")
        session.add_all([listing, run])
        session.flush()
        collector._apply_info(session, listing, data, NOW)
        snapshot = collector._snapshot(listing, run, NOW, in_search=True, response=httpx.Response(200, json=data))
        session.flush()
        session.expunge_all()
        return listing, snapshot, listing.location


def test_active_listing_is_stored_as_received(db):
    listing, snapshot, location = parse(db, "info_active")

    assert (listing.year, listing.gearbox, listing.body_type) == (2022, "Ручна / Механіка", "Родстер")
    assert (listing.fuel_type, listing.fuel_label) == ("Бензин", "Бензин, 2 л.")
    assert listing.vin == "JM1TESTFIXTURE0001" and listing.plate is None
    assert listing.dealer_type is None  # empty strings from the API become NULL
    assert listing.link.startswith("https://auto.ria.com/auto_mazda_mx_5_")
    assert listing.posted_at == datetime(2026, 10, 15, 11, 34, 48)
    assert location.city_name == "Дніпро (Дніпропетровськ)" and location.region_name == "Дніпропетровська"

    assert (snapshot.price_usd, snapshot.price_eur, snapshot.price_uah) == (28500, 25199, 1285920)
    assert (snapshot.main_currency, snapshot.mileage_k_km) == ("USD", 13)
    assert (snapshot.active, snapshot.is_sold, snapshot.from_archive, snapshot.status_id) == (True, False, False, 0)
    assert snapshot.update_date == datetime(2026, 10, 17, 8, 31, 2) and snapshot.sold_date is None
    assert snapshot.fetch_ok and snapshot.http_status == 200


def test_archived_listing_keeps_its_raw_status_flags(db):
    listing, snapshot, _ = parse(db, "info_archived")

    assert listing.plate == "AA 0000 AA"
    assert (snapshot.active, snapshot.from_archive, snapshot.on_moderation) == (False, True, True)
    assert (snapshot.status_id, snapshot.status_id5_type, snapshot.is_sold) == (5, 1, False)

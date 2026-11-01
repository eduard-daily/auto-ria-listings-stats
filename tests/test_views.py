"""The SQL views the UI reads: price changes must ignore exchange-rate noise."""
from datetime import datetime, timedelta

from sqlalchemy import select, text

from ria_stats.models import CollectionRun, Listing, ListingSnapshot, Model

DAY = datetime(2026, 11, 1)


def add_listing(session, auto_id: int) -> Listing:
    listing = Listing(ria_auto_id=auto_id, model_id=session.scalars(select(Model)).first().id, first_seen_at=DAY, last_seen_at=DAY)
    session.add(listing)
    session.flush()
    return listing


def add_snapshot(session, listing, number, *, currency="USD", usd=None, eur=None, uah=None, ok=True, in_search=True, is_sold=False):
    run = CollectionRun(started_at=DAY + timedelta(days=number), status="completed")
    session.add(run)
    session.flush()
    session.add(ListingSnapshot(
        listing_id=listing.id, run_id=run.id, observed_at=DAY + timedelta(days=number), main_currency=currency,
        price_usd=usd, price_eur=eur, price_uah=uah, in_search=in_search, fetch_ok=ok, is_sold=is_sold,
    ))


def test_price_changes_compare_the_sellers_own_currency(db):
    with db.begin() as session:
        usd_cut, rate_only, uah_cut = (add_listing(session, i) for i in (1, 2, 3))
        # a USD seller cuts the price; the converted prices drift as well
        add_snapshot(session, usd_cut, 0, usd=20000, eur=18000, uah=800000)
        add_snapshot(session, usd_cut, 1, usd=19500, eur=17500, uah=790000)
        # a UAH seller does not touch the price; only the exchange rate moves the USD figure
        add_snapshot(session, rate_only, 0, currency="UAH", usd=20000, uah=800000)
        add_snapshot(session, rate_only, 1, currency="UAH", usd=20800, uah=800000)
        # a UAH seller cuts the price; a failed fetch sits in between and must be skipped
        add_snapshot(session, uah_cut, 0, currency="UAH", usd=20000, uah=800000)
        add_snapshot(session, uah_cut, 1, currency=None, ok=False)
        add_snapshot(session, uah_cut, 2, currency="UAH", usd=19000, uah=760000)

    with db() as session:
        rows = session.execute(text("SELECT ria_auto_id, currency, was_price, now_price, diff FROM price_changes ORDER BY 1")).all()
    assert rows == [(1, "USD", 20000, 19500, -500), (3, "UAH", 800000, 760000, -40000)]


def test_listing_status_is_derived_from_the_latest_snapshot(db):
    with db.begin() as session:
        pending, active, sold, removed = (add_listing(session, i) for i in (1, 2, 3, 4))
        add_snapshot(session, active, 0, usd=15000)
        add_snapshot(session, sold, 0, usd=17000)
        add_snapshot(session, sold, 1, usd=17000, in_search=False, is_sold=True)
        add_snapshot(session, removed, 0, usd=12000)
        add_snapshot(session, removed, 1, usd=12000, in_search=False)

    with db() as session:
        status = dict(session.execute(text("SELECT ria_auto_id, status FROM listing_latest")).all())
    assert status == {1: "pending", 2: "active", 3: "sold", 4: "removed"}

import copy
import types

import httpx
import pytest
from sqlalchemy import func, select, text

from helpers import FakeRia, load_fixture
from ria_stats import backfill, collector, photo_store, photos
from ria_stats.models import CollectionRun, Listing, ListingPhoto, ListingSnapshot

LINK = "https://auto.ria.com/uk/auto_mazda_mx_5_39932487.html?utm_source=android&utm_medium=share_final_page"


def gone(auto_id: int, **changes) -> dict:
    """A tracked MX-5 that has left AUTO.RIA: inactive and archived."""
    data = copy.deepcopy(load_fixture("info_active"))
    data["autoData"].update(autoId=auto_id, active=False, fromArchive=True, statusId=14)
    data.update(changes)
    return data


@pytest.fixture
def cdn(monkeypatch):
    monkeypatch.setattr(photos, "time", types.SimpleNamespace(sleep=lambda _: None))  # no pause between photos
    jpeg = b"\xff\xd8\xff\xe0" + b"x" * 100
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=jpeg, headers={"content-type": "image/jpeg"})))


def rows(db, model) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_ids_and_links_are_both_accepted():
    assert backfill.parse_auto_id("39932487") == 39932487
    assert backfill.parse_auto_id(LINK) == 39932487
    with pytest.raises(ValueError):
        backfill.parse_auto_id("not a listing")


def test_a_gone_listing_is_added_with_its_final_state_and_photos(db, cdn):
    ria = FakeRia(payloads={39932487: gone(39932487)})

    [outcome] = backfill.backfill([39932487], client=ria, http=cdn)

    assert outcome.status == "added" and ria.requests_used == 1
    assert (outcome.photos.downloaded, outcome.photos.failed) == (6, 0)
    assert photo_store.path("39932487/661378109.jpg").is_file()
    with db() as session:
        listing = session.scalars(select(Listing)).one()
        snapshot = session.scalars(select(ListingSnapshot)).one()
        run = session.scalars(select(CollectionRun)).one()
        status = session.execute(text("SELECT status FROM listing_latest")).scalar_one()
    assert (listing.year, listing.last_in_search_at) == (2022, None)
    assert (snapshot.in_search, snapshot.fetch_ok, snapshot.price_usd, snapshot.status_id) == (False, True, 28500, 14)
    assert (run.trigger, run.requests_used, run.status) == ("backfill", 1, "completed")
    assert status == "removed"


def test_the_normal_cycle_leaves_a_backfilled_listing_alone(db, cdn):
    backfill.backfill([39932487], client=FakeRia(payloads={39932487: gone(39932487)}), http=cdn)

    with db() as session:
        assert collector.pending_count(session) == 0
    assert collector.collect(client=FakeRia()) is None
    assert rows(db, ListingSnapshot) == 1


def test_refusals_store_nothing(db):
    still_active = copy.deepcopy(load_fixture("info_active"))
    other_model = gone(2, markId=23, modelId=1, markName="Fiat", modelName="Barchetta")
    ria = FakeRia(payloads={1: still_active, 2: other_model, 3: 404})

    outcomes = backfill.backfill([1, 2, 3], client=ria)

    assert [o.status for o in outcomes] == ["active", "not_tracked", "not_found"]
    assert "tracked car" in outcomes[0].message and "discovery" in outcomes[0].message
    assert "not a tracked model" in outcomes[1].message
    assert rows(db, Listing) == 0 and rows(db, ListingSnapshot) == 0 and rows(db, ListingPhoto) == 0


def test_a_listing_already_in_the_database_costs_no_request(db, cdn):
    backfill.backfill([39932487], client=FakeRia(payloads={39932487: gone(39932487)}), http=cdn)

    ria = FakeRia()
    [outcome] = backfill.backfill([39932487], client=ria, http=cdn)

    assert outcome.status == "exists" and ria.requests_used == 0 and rows(db, ListingSnapshot) == 1


def test_a_rate_limit_stops_the_batch_but_keeps_what_was_added(db, cdn):
    ria = FakeRia(payloads={i: gone(i) for i in (11, 12, 13)}, rate_limit_after=1)

    outcomes = backfill.backfill([11, 12, 13], client=ria, http=cdn)

    assert [o.status for o in outcomes] == ["added", "rate_limited", "skipped"]
    assert rows(db, Listing) == 1
    with db() as session:
        assert session.scalar(select(CollectionRun.status)) == "rate_limited"


def test_a_malformed_response_does_not_stop_the_rest(db, cdn):
    broken = gone(21, addDate="not a date")
    ria = FakeRia(payloads={21: broken, 22: gone(22)})

    outcomes = backfill.backfill([21, 22], client=ria, http=cdn)

    assert [o.status for o in outcomes] == ["failed", "added"]
    assert rows(db, Listing) == 1  # nothing half-stored for the broken one

"""The refresh cycle: discovery, then detail collection in capped, resumable slices."""
import httpx
import pytest
from sqlalchemy import func, select

from helpers import SECRET_KEY, FakeRia
from ria_stats import collector, discovery
from ria_stats.models import DiscoveryRun, Listing, ListingSnapshot

IDS = [101, 102, 103, 104, 105]


def discover(db, ids=IDS, force=False, client=None):
    with db() as session:
        return discovery.discover(session, client or FakeRia(ids), force=force)


def count(db, model) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_discovery_stores_stubs_and_is_due_again_after_two_days(db, age_days):
    [run] = discover(db)
    assert (run.status, run.ids_returned, run.trigger) == ("completed", 5, "manual")
    assert count(db, Listing) == 5

    assert discover(db) == []  # same day: not due
    age_days(1)
    assert discover(db) == []  # one day old: still not due
    age_days(1)
    assert len(discover(db)) == 1  # two days old: due
    assert len(discover(db, force=True)) == 1  # force ignores the schedule


def test_rate_limited_discovery_leaves_nothing_behind(db):
    [run] = discover(db, client=FakeRia(IDS, rate_limit_after=0))

    assert run.status == "rate_limited" and run.search_total is None
    assert count(db, Listing) == 0
    assert discover(db)[0].status == "completed"  # the next attempt starts clean


def test_collect_fetches_each_listing_once_per_cycle(db):
    discover(db)
    run = collector.collect(client=FakeRia())

    assert (run.status, run.requests_used) == ("completed", 5)
    assert count(db, ListingSnapshot) == 5
    assert collector.collect(client=FakeRia()) is None  # nothing left in this cycle


def test_request_cap_splits_a_cycle_into_resumable_runs(db):
    discover(db)

    assert collector.collect(max_requests=3, client=FakeRia()).requests_used == 3
    assert collector.collect(max_requests=3, client=FakeRia()).requests_used == 2
    assert collector.collect(max_requests=3, client=FakeRia()) is None
    assert count(db, ListingSnapshot) == 5


def test_rate_limit_mid_run_keeps_progress_and_the_next_run_continues(db):
    discover(db)

    limited = collector.collect(client=FakeRia(rate_limit_after=2))
    assert limited.status == "rate_limited" and count(db, ListingSnapshot) == 2

    assert collector.collect(client=FakeRia()).requests_used == 3
    assert count(db, ListingSnapshot) == 5


def test_a_failed_fetch_is_recorded_and_not_retried_in_the_same_cycle(db):
    discover(db)
    collector.collect(client=FakeRia(missing={103}))

    with db() as session:
        failed = session.scalars(select(ListingSnapshot).where(ListingSnapshot.fetch_ok.is_(False))).one()
    assert failed.http_status == 404
    assert collector.collect(client=FakeRia()) is None


def test_a_listing_that_left_search_gets_exactly_one_final_fetch(db, age_days):
    discover(db)
    collector.collect(client=FakeRia())
    age_days(3)

    discover(db, ids=IDS[:-1])  # 105 is gone from search; a new cycle starts
    run = collector.collect(client=FakeRia())
    assert run.requests_used == 5  # four still listed, plus the departed one

    with db() as session:
        last = session.scalars(
            select(ListingSnapshot).join(Listing).where(Listing.ria_auto_id == 105).order_by(ListingSnapshot.id.desc())
        ).first()
    assert last.in_search is False

    age_days(3)
    discover(db, ids=IDS[:-1])
    assert collector.collect(client=FakeRia()).requests_used == 4  # 105 is not fetched again


def test_fetching_one_listing_by_hand(db):
    discover(db)

    run = collector.collect(client=FakeRia(), auto_id=102)
    assert run.requests_used == 1 and count(db, ListingSnapshot) == 1

    with pytest.raises(LookupError):
        collector.collect(client=FakeRia(), auto_id=999)


def test_a_failed_search_is_recorded_without_the_api_key(db):
    [run] = discover(db, client=FakeRia(IDS, search_status=403))

    assert run.status == "failed" and "HTTP 403" in run.errors
    with db() as session:
        stored = session.scalar(select(DiscoveryRun.errors))
    assert SECRET_KEY not in run.errors and SECRET_KEY not in stored


def test_one_malformed_response_does_not_block_the_rest_of_the_run(db):
    discover(db)

    run = collector.collect(client=FakeRia(bad={102}))
    assert run.status == "completed_with_errors" and "102" in run.errors
    assert run.requests_used == 5  # the listings after the bad one were still fetched

    with db() as session:
        snapshots = {s.listing.ria_auto_id: s for s in session.scalars(select(ListingSnapshot))}
        bad = session.scalars(select(Listing).where(Listing.ria_auto_id == 102)).one()
        assert (snapshots[102].fetch_ok, snapshots[102].http_status) == (False, 200)  # a 200 that was unusable
        assert all(snapshots[i].fetch_ok for i in (101, 103, 104, 105))
        assert bad.year is None and bad.photos_synced_at is None  # nothing half-applied was kept

    assert collector.collect(client=FakeRia()) is None  # not retried within the same cycle


def test_a_network_error_that_mentions_the_url_is_stored_without_the_api_key(db):
    leaky = httpx.ConnectError(f"cannot reach https://developers.ria.com/auto/search?api_key={SECRET_KEY}&page=0")

    [run] = discover(db, client=FakeRia(IDS, error=leaky))
    assert run.status == "failed" and SECRET_KEY not in run.errors and "api_key=***" in run.errors

    discover(db)  # a real discovery, so there is something to fetch
    run = collector.collect(client=FakeRia(error=leaky))
    assert SECRET_KEY not in run.errors and "api_key=***" in run.errors

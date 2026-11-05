from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient
from sqlalchemy import select

from helpers import FakeRia, load_fixture
from ria_stats import api, collector, discovery, photos, scheduler, settings
from ria_stats.models import ListingPhoto

from test_photos import add_listing


def put(client, **changes):
    current = client.get("/api/settings").json()["values"]
    return client.put("/api/settings", json={**current, **changes})


def test_settings_default_until_saved_and_bad_values_are_refused(db):
    client = TestClient(api.app)
    body = client.get("/api/settings").json()
    assert body["values"] == body["defaults"] and body["limits"]["max_requests"] == [1, 30]

    ok = put(client, refresh_days=3, run_hours=[14, 12, 12], scheduler_enabled=False)
    assert ok.status_code == 200 and ok.json()["values"]["run_hours"] == [12, 14]  # sorted, no duplicates
    assert client.get("/api/settings").json()["values"]["refresh_days"] == 3  # kept

    for bad in ({"refresh_days": 0}, {"max_requests": 31}, {"run_hours": []}, {"run_hours": [24]},
                {"max_photos_per_listing": 501}):
        assert put(client, **bad).status_code == 422
    assert client.get("/api/settings").json()["values"]["refresh_days"] == 3  # nothing half applied


def test_runs_use_the_saved_settings(db, age_days):
    with db.begin() as session:
        settings.save(session, settings.Settings(refresh_days=1, max_requests=2, max_photos_per_listing=5))

    with db() as session:
        discovery.discover(session, FakeRia([101, 102, 103]))
    assert collector.collect(client=FakeRia()).requests_used == 2  # the saved cap, not 28

    age_days(1)
    with db() as session:
        assert len(discovery.discover(session, FakeRia([101, 102, 103]))) == 1  # due after one day, not two

    data = load_fixture("info_active")
    data["photoData"] = {"all": list(range(1000, 1400))}
    with db.begin() as session:
        listing = add_listing(session, 999)
        photos.sync_photos(session, listing, data, photos.utcnow())
        assert len(session.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)).all()) == 5


def test_the_scheduler_follows_the_settings(db):
    jobs = BackgroundScheduler()
    jobs.add_job(scheduler.run_collection, id=scheduler.JOB_ID, trigger="interval", hours=1)
    jobs.start(paused=True)
    try:
        with db.begin() as session:
            settings.save(session, settings.Settings(run_hours=[7, 9], scheduler_enabled=False))
        scheduler.apply_settings(jobs)
        job = jobs.get_job(scheduler.JOB_ID)
        assert job.next_run_time is None and "hour='7,9'" in str(job.trigger)  # paused, at the saved hours

        with db.begin() as session:
            settings.save(session, settings.Settings(run_hours=[7, 9], scheduler_enabled=True))
        scheduler.apply_settings(jobs)
        assert jobs.get_job(scheduler.JOB_ID).next_run_time is not None
    finally:
        jobs.shutdown(wait=False)

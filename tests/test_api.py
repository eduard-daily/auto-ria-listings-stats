import pytest
from fastapi.testclient import TestClient

from helpers import FakeRia
from ria_stats import api, collector, discovery, locking, photo_store, update
from ria_stats.photos import PhotoResult

IDS = [101, 102, 103]


@pytest.fixture
def client(db):
    with db() as session:
        discovery.discover(session, FakeRia(IDS))
    collector.collect(client=FakeRia())
    return TestClient(api.app)  # no `with`: the scheduler in the app's lifespan stays off


def test_listings_can_be_filtered_and_bad_input_is_rejected(client):
    assert len(client.get("/api/listings").json()) == 3
    assert len(client.get("/api/listings", params={"status": "sold"}).json()) == 0
    assert len(client.get("/api/listings", params={"model_id": 999}).json()) == 0
    assert client.get("/api/listings", params={"status": "bogus"}).status_code == 422
    assert client.get("/api/listings/1").status_code == 404


def test_timestamps_of_ours_are_utc_and_the_detail_has_the_full_history(client):
    detail = client.get("/api/listings/101").json()

    assert detail["first_seen_at"].endswith("Z") and detail["snapshots"][0]["observed_at"].endswith("Z")
    assert len(detail["snapshots"]) == 1 and detail["snapshots"][0]["listed_price"] == 10101
    assert detail["status"] == "active" and detail["vin"] == "JM1TESTFIXTURE0001"
    assert len(detail["photos"]) == 0  # nothing downloaded yet


def test_every_action_answers_409_while_another_update_runs(client):
    with locking.update_lock():
        assert client.post("/api/update").status_code == 409
        assert client.post("/api/discovery/force").status_code == 409
        assert client.post("/api/listings/101/refresh").status_code == 409
        assert client.get("/api/stats").json()["update_running"] is True
    assert client.post("/api/listings/999/refresh").status_code == 404


def test_the_update_button_runs_an_update_and_records_it_as_manual(client, age_days, monkeypatch):
    age_days(3)  # a new cycle is due
    monkeypatch.setattr(update, "RiaClient", lambda: FakeRia(IDS))
    monkeypatch.setattr(update, "download_pending", lambda **_: PhotoResult(downloaded=7, remaining=3))

    body = client.post("/api/update").json()

    assert [d["trigger"] for d in body["discoveries"]] == ["manual"] and body["collection"]["trigger"] == "manual"
    assert body["collection"]["requests_used"] == 3
    assert body["photos"] == {"downloaded": 7, "gone": 0, "failed": 0, "remaining": 3}


def test_photos_are_served_as_immutable_files_and_paths_cannot_escape(client):
    photo_store.save("101/555.jpg", b"\xff\xd8\xff data")

    served = client.get("/api/photos/101/555.jpg")
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"
    assert "immutable" in served.headers["cache-control"]

    for bad in ("/api/photos/101/..%2F..%2Fria.db", "/api/photos/101/555.png", "/api/photos/101/x.jpg", "/api/photos/999/555.jpg"):
        assert client.get(bad).status_code == 404


def test_writes_from_another_origin_are_refused_but_normal_clients_pass(client):
    writes = ("/api/update", "/api/discovery/force", "/api/listings/101/refresh")
    with locking.update_lock():  # so a request that gets through answers 409 instead of running anything
        for path in writes:
            assert client.post(path, headers={"Origin": "https://evil.example"}).status_code == 403
            assert client.post(path, headers={"Origin": "null"}).status_code == 403
            assert client.post(path, headers={"Origin": "http://testserver"}).status_code == 409  # this host
            assert client.post(path).status_code == 409  # curl, scripts: no Origin header
    assert client.get("/api/stats", headers={"Origin": "https://evil.example"}).status_code == 200  # reads stay open

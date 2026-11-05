import re

import httpx
from sqlalchemy import delete, select

from helpers import FakeRia, load_fixture
from ria_stats import collector, discovery, photo_store, photos
from ria_stats.models import Listing, ListingPhoto, Model

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 100


def add_listing(session, auto_id=1) -> Listing:
    listing = Listing(ria_auto_id=auto_id, model_id=session.scalars(select(Model)).first().id,
                      first_seen_at=photos.utcnow(), last_seen_at=photos.utcnow())
    session.add(listing)
    session.flush()
    return listing


def test_photos_are_recorded_once_with_the_cover_flagged(db):
    data = load_fixture("info_active")  # six photos; the cover is the third id
    with db.begin() as session:
        listing = add_listing(session)
        photos.sync_photos(session, listing, data, photos.utcnow())
        # the seller changes the photos later: ignored
        photos.sync_photos(session, listing, {**data, "photoData": {"all": [1, 2], "count": 2}}, photos.utcnow())
        rows = session.scalars(select(ListingPhoto).order_by(ListingPhoto.position)).all()

        assert [r.ria_photo_id for r in rows] == data["photoData"]["all"]
        assert [r.ria_photo_id for r in rows if r.is_cover] == [661378101]
        assert {r.status for r in rows} == {"pending"} and rows[0].url_slug == "mazda_mx-5"

        bare = add_listing(session, 2)  # a listing without photos is marked done, so it is not refetched forever
        photos.sync_photos(session, bare, {**data, "photoData": {"all": [], "count": 0}}, photos.utcnow())
        assert bare.photos_synced_at is not None


def test_only_the_cover_and_the_first_photos_are_recorded_for_a_huge_listing(db):
    cap = 40
    data = load_fixture("info_active")
    ids = list(range(1000, 1400))  # 400 photos, the cover is the last one
    data["photoData"] = {"all": ids, "seoLinkB": f"https://x/mazda_mx-5__{ids[-1]}b.jpg"}
    with db.begin() as session:
        photos.sync_photos(session, add_listing(session), data, photos.utcnow())
        rows = session.scalars(select(ListingPhoto).order_by(ListingPhoto.position)).all()

        assert len(rows) == cap + 1
        assert [r.ria_photo_id for r in rows][:-1] == ids[:cap]
        assert rows[-1].ria_photo_id == ids[-1] and rows[-1].is_cover


def fake_cdn(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        photo_id, variant = re.search(r"__(\d+)(hd|f)\.jpg", str(request.url)).groups()
        calls.append((int(photo_id), variant))
        if photo_id == "661378108" and variant == "hd":
            return httpx.Response(404)  # no hd, but f exists
        if photo_id == "661378107":
            return httpx.Response(404)  # no size exists
        if photo_id == "661380164":
            return httpx.Response(500)  # server error
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_fall_back_to_a_smaller_size_and_classify_failures(db):
    calls: list = []
    with db.begin() as session:
        photos.sync_photos(session, add_listing(session, 101), load_fixture("info_active"), photos.utcnow())

    result = photos.download_pending(delay=0, http=fake_cdn(calls))
    assert (result.downloaded, result.gone, result.failed) == (4, 1, 1)
    assert calls[0][0] == 661378101  # the cover first

    with db() as session:
        by_id = {p.ria_photo_id: p for p in session.scalars(select(ListingPhoto))}
    assert (by_id[661378109].status, by_id[661378109].variant) == ("ok", "hd")
    assert (by_id[661378108].status, by_id[661378108].variant) == ("ok", "f")
    assert by_id[661378107].status == "gone" and by_id[661380164].status == "failed"
    assert photo_store.path("101/661378109.jpg").read_bytes() == JPEG


def test_a_photo_is_never_downloaded_twice_and_the_cap_is_respected(db):
    calls: list = []
    with db.begin() as session:
        photos.sync_photos(session, add_listing(session, 101), load_fixture("info_active"), photos.utcnow())

    first = photos.download_pending(max_photos=2, delay=0, http=fake_cdn(calls))
    assert first.downloaded == 2 and first.remaining == 4

    calls.clear()
    photos.download_pending(delay=0, http=fake_cdn(calls))  # finishes the rest
    calls.clear()
    photos.download_pending(delay=0, http=fake_cdn(calls))  # only the failed one is retried
    assert {photo_id for photo_id, _ in calls} == {661380164}


def test_listings_whose_photos_were_never_recorded_are_fetched_again(db):
    with db() as session:
        discovery.discover(session, FakeRia([101, 102]))
    collector.collect(client=FakeRia())
    assert collector.collect(client=FakeRia()) is None

    with db.begin() as session:  # as if it had been fetched before photos existed: no flag, no rows
        listing = session.scalars(select(Listing).where(Listing.ria_auto_id == 101)).one()
        listing.photos_synced_at = None
        session.execute(delete(ListingPhoto).where(ListingPhoto.listing_id == listing.id))
    with db() as session:
        assert collector.pending_count(session) == 1

    assert collector.collect(client=FakeRia()).requests_used == 1
    assert collector.collect(client=FakeRia()) is None

"""Listing photos: remember which photos each listing has, then download every photo once.

/auto/info lists a listing's photo ids and the cover. sync_photos records them as pending rows,
once, when the listing is first fetched. download_pending fetches the pending ones from the image
CDN (not the API, so no API quota) in the largest size, falling back to a smaller one. A photo
is never downloaded twice.
"""
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ria_stats import photo_store
from ria_stats.config import MAX_PHOTOS, PHOTO_DELAY, utcnow
from ria_stats.db import SessionLocal
from ria_stats.models import Listing, ListingPhoto
from ria_stats.settings import load as load_settings

# Any of cdn0..cdn3 serves the same file. Sizes: hd 1280x853, f 800x600 (cropped), b/m/sx 380x250.
CDN_URL = "https://cdn1.riastatic.com/photosnew/auto/photo/{slug}__{photo_id}{variant}.jpg"
VARIANTS = ("hd", "f")  # tried in this order
COVER_PATTERN = re.compile(r"__(\d+)b\.jpg")
MAX_CONSECUTIVE_FAILURES = 5  # stop early when the CDN is clearly unreachable

log = logging.getLogger("ria_stats.photos")


@dataclass
class PhotoResult:
    downloaded: int = 0
    gone: int = 0
    failed: int = 0
    remaining: int = 0


def sync_photos(session: Session, listing: Listing, data: dict, now: datetime) -> None:
    """Record the photos in an /auto/info response, the first time only.

    Photos the seller adds or removes later are ignored. Only the cover and the first photos, up
    to the max_photos_per_listing setting, are recorded. A listing without photos is marked as synced too, so
    it is not fetched again just for photos.
    """
    if listing.photos_synced_at is not None:
        return
    listing.photos_synced_at = now

    photo_data = data.get("photoData") or {}
    ids = photo_data.get("all") or []
    if not ids or not data.get("markNameEng") or not data.get("modelNameEng"):
        return
    slug = f'{data["markNameEng"]}_{data["modelNameEng"]}'
    cover = COVER_PATTERN.search(photo_data.get("seoLinkB") or "")
    cover_id = int(cover.group(1)) if cover else None
    kept = set(ids[:load_settings(session).max_photos_per_listing])
    if cover_id in ids:
        kept.add(cover_id)
    for position, photo_id in enumerate(ids):
        if photo_id not in kept:
            continue
        session.add(ListingPhoto(listing_id=listing.id, ria_photo_id=photo_id, url_slug=slug, position=position,
                                 is_cover=photo_id == cover_id, first_seen_at=now))


def _fetch(http: httpx.Client, photo: ListingPhoto) -> tuple[str, str | None, bytes | None, int | None]:
    """Return (status, variant, content, http status) for one photo, trying each size."""
    status = None
    for variant in VARIANTS:
        response = http.get(CDN_URL.format(slug=photo.url_slug, photo_id=photo.ria_photo_id, variant=variant))
        status = response.status_code
        if status == 404:
            continue  # this size does not exist; try the next
        if status == 200 and response.headers.get("content-type", "").startswith("image/") and response.content:
            return "ok", variant, response.content, status
        return "failed", None, None, status
    return "gone", None, None, status


def download_pending(max_photos: int = MAX_PHOTOS, delay: float = PHOTO_DELAY, listing_id: int | None = None,
                     http: httpx.Client | None = None) -> PhotoResult:
    """Download pending and failed photos, covers first, at most max_photos per call.

    The caller holds the update lock. Pass a listing id to fetch only that listing's photos.
    """
    result = PhotoResult()
    own_http = http is None
    http = http or httpx.Client(timeout=30)
    consecutive_failures = 0
    try:
        with SessionLocal() as session:
            query = (
                select(ListingPhoto, Listing.ria_auto_id)
                .join(Listing, Listing.id == ListingPhoto.listing_id)
                .where(ListingPhoto.status.in_(("pending", "failed")))
                .order_by(ListingPhoto.is_cover.desc(), ListingPhoto.listing_id, ListingPhoto.position)
            )
            if listing_id is not None:
                query = query.where(ListingPhoto.listing_id == listing_id)
            todo = session.execute(query).all()
            result.remaining = len(todo)
            if todo:
                log.info("%s photos to download, cap %s", len(todo), max_photos)

            for photo, auto_id in todo[:max_photos]:
                try:
                    status, variant, content, http_status = _fetch(http, photo)
                except httpx.HTTPError as e:
                    log.warning("photo %s of listing %s: %r", photo.ria_photo_id, auto_id, e)
                    status, variant, content, http_status = "failed", None, None, None
                photo.status, photo.http_status = status, http_status
                if status == "ok":
                    photo.variant = variant
                    photo.key = f"{auto_id}/{photo.ria_photo_id}.jpg"
                    photo.size_bytes = len(content)
                    photo.downloaded_at = utcnow()
                    photo_store.save(photo.key, content)
                    result.downloaded += 1
                    consecutive_failures = 0
                elif status == "gone":
                    result.gone += 1
                    consecutive_failures = 0
                else:
                    result.failed += 1
                    consecutive_failures += 1
                session.commit()
                result.remaining -= 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    log.warning("%s failures in a row, giving up until the next update", consecutive_failures)
                    break
                time.sleep(delay)
    finally:
        if own_http:
            http.close()
    if result.downloaded or result.gone or result.failed:
        log.info("photos: %s downloaded, %s gone, %s failed, %s remaining", result.downloaded, result.gone,
                 result.failed, result.remaining)
    return result

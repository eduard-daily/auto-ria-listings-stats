"""Settings shared by discovery, the collector and the scheduler."""
from datetime import UTC, datetime

# RIA ids of the tracked (brand, model) pairs; widening the scope means adding pairs here.
TRACKED = [(47, 399)]  # Mazda MX-5

MAX_REQUESTS = 28  # per wake-up, discovery and details together; the free package allows 30 per hour
REFRESH_DAYS = 2  # a model is rediscovered, and its listings refetched, every this many calendar days

MAX_PHOTOS = 40  # photo downloads per update; they come from the image CDN, not the API
PHOTO_DELAY = 0.3  # seconds between photo downloads


def utcnow() -> datetime:
    """Our own timestamps are naive UTC (see models.py)."""
    return datetime.now(UTC).replace(tzinfo=None)

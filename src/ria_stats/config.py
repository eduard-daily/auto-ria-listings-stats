"""Settings shared by discovery, the collector and the scheduler."""
from datetime import UTC, datetime

# RIA ids of the tracked (brand, model) pairs; widening the scope means adding pairs here.
TRACKED = [(47, 399)]  # Mazda MX-5

# The values below up to PHOTO_DELAY are only the defaults of the settings (see settings.py), which
# the Settings page changes.
MAX_REQUESTS = 28  # per wake-up, discovery and details together; the free package allows 30 per hour
REFRESH_DAYS = 2  # a model is rediscovered, and its listings refetched, every this many calendar days

RUN_HOURS = list(range(12, 19))  # hours of the day (Europe/Kyiv, see TZ in docker-compose.yml) a scheduled run may start

MAX_PHOTOS = 200  # photo downloads per update; they come from the image CDN, not the API
MAX_PHOTOS_PER_LISTING = 40  # photos recorded (and so downloaded) per listing; the cover is always kept
PHOTO_DELAY = 0.3  # seconds between photo downloads


def utcnow() -> datetime:
    """Our own timestamps are naive UTC (see models.py)."""
    return datetime.now(UTC).replace(tzinfo=None)

"""Settings the Settings page changes. They live in the `settings` table as JSON, one row per key;
a key without a row has its default from config.py. Everything that runs reads them when it runs,
so a change applies from the next run on.
"""
import json
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ria_stats.config import MAX_PHOTOS_PER_LISTING, MAX_REQUESTS, REFRESH_DAYS, RUN_HOURS, utcnow
from ria_stats.models import Setting

log = logging.getLogger("ria_stats.settings")

# (smallest, largest). The request cap tops out at 30, the free plan's hourly limit.
LIMITS = {"refresh_days": (1, 30), "max_photos_per_listing": (1, 500), "max_requests": (1, 30)}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_days: int = Field(REFRESH_DAYS, ge=LIMITS["refresh_days"][0], le=LIMITS["refresh_days"][1])
    run_hours: list[int] = Field(default_factory=lambda: list(RUN_HOURS), min_length=1)
    scheduler_enabled: bool = True
    max_requests: int = Field(MAX_REQUESTS, ge=LIMITS["max_requests"][0], le=LIMITS["max_requests"][1])
    max_photos_per_listing: int = Field(
        MAX_PHOTOS_PER_LISTING, ge=LIMITS["max_photos_per_listing"][0], le=LIMITS["max_photos_per_listing"][1])

    @field_validator("run_hours")
    @classmethod
    def _hours(cls, hours: list[int]) -> list[int]:
        if any(not 0 <= h <= 23 for h in hours):
            raise ValueError("hours must be between 0 and 23")
        return sorted(set(hours))


def load(session: Session) -> Settings:
    stored = {row.key: json.loads(row.value) for row in session.scalars(select(Setting))}
    try:
        return Settings(**{k: v for k, v in stored.items() if k in Settings.model_fields})
    except ValidationError:
        log.exception("stored settings are invalid, using the defaults")
        return Settings()


def save(session: Session, settings: Settings) -> None:
    now = utcnow()
    for key, value in settings.model_dump().items():
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=json.dumps(value), updated_at=now))
        elif json.loads(row.value) != value:
            row.value, row.updated_at = json.dumps(value), now

"""The update operations behind the scheduler's wake-up and the web buttons.

Each one takes the update lock and raises UpdateInProgress when another update holds it.
"""
from dataclasses import dataclass

from ria_stats.client import RiaClient
from ria_stats.collector import collect
from ria_stats.db import SessionLocal
from ria_stats.discovery import discover
from ria_stats.locking import update_lock
from ria_stats.models import CollectionRun, DiscoveryRun


@dataclass
class UpdateResult:
    discoveries: list[DiscoveryRun]
    collection: CollectionRun | None  # None: nothing to fetch, or discovery was rate limited


def run_update(trigger: str, force: bool = False) -> UpdateResult:
    """Discovery if due (always with force), then detail collection; one request cap for both."""
    with update_lock():
        client = RiaClient()
        try:
            with SessionLocal() as session:
                discoveries = discover(session, client, trigger=trigger, force=force)
            if any(d.status == "rate_limited" for d in discoveries):
                return UpdateResult(discoveries, None)
            return UpdateResult(discoveries, collect(client=client, trigger=trigger))
        finally:
            client.close()


def refresh_listing(auto_id: int, trigger: str = "manual") -> CollectionRun:
    """Fetch one listing now, whether or not it is pending. LookupError if the id is unknown."""
    with update_lock():
        client = RiaClient()
        try:
            run = collect(client=client, trigger=trigger, auto_id=auto_id)
        finally:
            client.close()
    assert run is not None  # a single target is never "nothing to do"
    return run

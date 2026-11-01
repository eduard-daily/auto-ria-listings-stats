"""File lock so only one update (discovery or detail collection) runs at a time.

Every entry point that spends API requests takes it: the CLI commands, the scheduler's wake-up
and the web actions. A second caller does not wait; it gets UpdateInProgress. The lock is
released when the holder exits, even if it crashes, and it works across containers because
they share the data/ volume.
"""
import fcntl
from contextlib import contextmanager

from ria_stats.db import DB_PATH

LOCK_PATH = DB_PATH.with_name("update.lock")


class UpdateInProgress(Exception):
    """Another update holds the lock."""


@contextmanager
def update_lock():
    with open(LOCK_PATH, "a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateInProgress("another update is running") from None
        yield


def update_running() -> bool:
    """Whether some update holds the lock right now (a momentary peek, not a reservation)."""
    try:
        with update_lock():
            return False
    except UpdateInProgress:
        return True

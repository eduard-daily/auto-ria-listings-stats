"""File lock so only one update (discovery or detail collection) runs at a time.

Every entry point that spends API requests takes it: the CLI commands, the scheduler's wake-up
and the web actions. A second caller does not wait; it gets UpdateInProgress. The lock is
released when the holder exits, even if it crashes, and it works across containers because
they share the data/ volume.
"""
import fcntl
import time
from contextlib import contextmanager

from ria_stats.db import DB_PATH

LOCK_PATH = DB_PATH.with_name("update.lock")
GRACE_SECONDS = 0.2  # how long to keep trying before deciding another update really is running


class UpdateInProgress(Exception):
    """Another update holds the lock."""


@contextmanager
def update_lock():
    with open(LOCK_PATH, "a") as lock_file:
        deadline = time.monotonic() + GRACE_SECONDS
        while True:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                # Not a queue: an update that really runs holds the lock far longer than the grace
                # period. It covers a status check (update_running) that holds it for an instant.
                if time.monotonic() >= deadline:
                    raise UpdateInProgress("another update is running") from None
                time.sleep(0.01)
        yield


def update_running() -> bool:
    """Whether some update holds the lock right now. Takes a shared lock for a moment, which
    does not conflict with other status checks and only delays an update by an instant."""
    with open(LOCK_PATH, "a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False

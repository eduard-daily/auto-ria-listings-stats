import subprocess
import sys
import threading

import pytest

from ria_stats import locking


def test_a_second_update_is_refused_while_another_holds_the_lock(db):
    holder = subprocess.Popen(
        [sys.executable, "-c", f"import fcntl, time; f = open({str(locking.LOCK_PATH)!r}, 'a'); "
                               "fcntl.flock(f, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        assert locking.update_running()
        with pytest.raises(locking.UpdateInProgress):
            with locking.update_lock():
                pytest.fail("got the lock while another process held it")
    finally:
        holder.kill()
        holder.wait()

    assert not locking.update_running()  # released when the holder died
    with locking.update_lock():
        pass


def test_status_checks_never_make_a_real_update_fail(db):
    """/api/stats peeks at the lock; an update starting at that instant must not be refused."""
    stop = threading.Event()
    checker = threading.Thread(target=lambda: [locking.update_running() for _ in iter(stop.is_set, True)])
    checker.start()
    refused = 0
    try:
        for _ in range(400):
            try:
                with locking.update_lock():
                    pass
            except locking.UpdateInProgress:
                refused += 1
    finally:
        stop.set()
        checker.join()
    assert refused == 0


def test_status_checks_do_not_see_each_other_as_a_running_update(db):
    seen = []
    checkers = [threading.Thread(target=lambda: seen.extend(locking.update_running() for _ in range(300))) for _ in range(2)]
    for checker in checkers:
        checker.start()
    for checker in checkers:
        checker.join()
    assert seen and not any(seen)

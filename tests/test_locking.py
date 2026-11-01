import subprocess
import sys

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

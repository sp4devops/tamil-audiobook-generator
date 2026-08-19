from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

from tamil_audiobook.locking import InterProcessRLock


def _wait_for_lock(path: str, attempting, acquired) -> None:
    attempting.set()
    with InterProcessRLock(Path(path)):
        acquired.set()


def test_interprocess_lock_blocks_other_process(tmp_path: Path):
    lock_path = tmp_path / "library.lock"
    ctx = mp.get_context("spawn")
    attempting = ctx.Event()
    acquired = ctx.Event()

    with InterProcessRLock(lock_path):
        process = ctx.Process(target=_wait_for_lock, args=(str(lock_path), attempting, acquired))
        process.start()
        assert attempting.wait(timeout=5)
        time.sleep(0.15)
        assert not acquired.is_set()

    assert acquired.wait(timeout=5)
    process.join(timeout=5)
    assert process.exitcode == 0
    assert lock_path.stat().st_mode & 0o777 == 0o600


def test_interprocess_lock_is_reentrant(tmp_path: Path):
    lock = InterProcessRLock(tmp_path / "library.lock")
    with lock:
        with lock:
            pass

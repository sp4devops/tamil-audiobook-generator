from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

from tamil_audiobook.locking import InterProcessRLock


def _wait_for_lock(path: str, acquired, queue) -> None:
    started = time.monotonic()
    with InterProcessRLock(Path(path)):
        queue.put(time.monotonic() - started)
        acquired.set()


def test_interprocess_lock_blocks_other_process(tmp_path: Path):
    lock_path = tmp_path / "library.lock"
    ctx = mp.get_context("spawn")
    acquired = ctx.Event()
    queue = ctx.Queue()

    with InterProcessRLock(lock_path):
        process = ctx.Process(target=_wait_for_lock, args=(str(lock_path), acquired, queue))
        process.start()
        assert not acquired.wait(timeout=0.3)

    assert acquired.wait(timeout=5)
    process.join(timeout=5)
    assert process.exitcode == 0
    waited = queue.get(timeout=1)
    assert waited >= 0.2
    assert lock_path.stat().st_mode & 0o777 == 0o600


def test_interprocess_lock_is_reentrant(tmp_path: Path):
    lock = InterProcessRLock(tmp_path / "library.lock")
    with lock:
        with lock:
            pass

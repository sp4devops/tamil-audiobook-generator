from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

from tamil_audiobook.locking import InterProcessRLock


def _wait_for_lock(path: str, queue) -> None:
    started = time.monotonic()
    with InterProcessRLock(Path(path)):
        queue.put(time.monotonic() - started)


def test_interprocess_lock_blocks_other_process(tmp_path: Path):
    lock_path = tmp_path / "library.lock"
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()

    with InterProcessRLock(lock_path):
        process = ctx.Process(target=_wait_for_lock, args=(str(lock_path), queue))
        process.start()
        time.sleep(0.35)
        assert queue.empty()

    process.join(timeout=5)
    assert process.exitcode == 0
    waited = queue.get(timeout=1)
    assert waited >= 0.25
    assert lock_path.stat().st_mode & 0o777 == 0o600


def test_interprocess_lock_is_reentrant(tmp_path: Path):
    lock = InterProcessRLock(tmp_path / "library.lock")
    with lock:
        with lock:
            pass

from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path


class InterProcessRLock:
    """Thread-reentrant lock that also serializes cooperating processes.

    The in-process RLock prevents sibling threads from sharing the file-lock
    descriptor concurrently. The outermost acquisition takes an advisory
    exclusive flock; nested acquisitions in the same thread only increase the
    depth, so normal LocalLibrary method nesting remains safe.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._thread_lock = threading.RLock()
        self._local = threading.local()

    def acquire(self) -> bool:
        self._thread_lock.acquire()
        depth = getattr(self._local, "depth", 0)
        if depth == 0:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                os.fchmod(fd, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
            except Exception:
                os.close(fd)
                self._thread_lock.release()
                raise
            self._local.fd = fd
        self._local.depth = depth + 1
        return True

    def release(self) -> None:
        depth = getattr(self._local, "depth", 0)
        if depth <= 0:
            raise RuntimeError("cannot release un-acquired InterProcessRLock")
        depth -= 1
        self._local.depth = depth
        try:
            if depth == 0:
                fd = self._local.fd
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
                    del self._local.fd
        finally:
            self._thread_lock.release()

    def __enter__(self) -> "InterProcessRLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

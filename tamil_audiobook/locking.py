from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path


class LockBusyError(RuntimeError):
    """Raised when a requested non-blocking advisory lock is already owned."""


class InterProcessRLock:
    """Thread-reentrant lock that also serializes cooperating processes.

    The in-process RLock prevents sibling threads from sharing the file-lock
    descriptor concurrently. The outermost acquisition takes an advisory
    exclusive flock; nested acquisitions in the same thread only increase the
    depth, so normal LocalLibrary method nesting remains safe.

    A LocalLibrary passes ``<root>/.library.lock`` as its logical lock path.
    The physical lock is stored as a sibling of ``root`` so deleting/resetting
    the library directory cannot replace the inode while another process is
    still holding the lock. Generation uses the same design with a distinct
    ``.generation.lock`` path and non-blocking acquisition.
    """

    def __init__(self, path: Path):
        requested = Path(path)
        if requested.name in {".library.lock", ".generation.lock"}:
            kind = requested.name.strip(".")
            requested = requested.parent.parent / f".{requested.parent.name}.{kind}"
        self.path = requested
        self._thread_lock = threading.RLock()
        self._local = threading.local()

    def acquire(self, *, blocking: bool = True) -> bool:
        thread_acquired = self._thread_lock.acquire(blocking=blocking)
        if not thread_acquired:
            return False
        depth = getattr(self._local, "depth", 0)
        if depth == 0:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                os.fchmod(fd, 0o600)
                operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                fcntl.flock(fd, operation)
            except BlockingIOError:
                os.close(fd)
                self._thread_lock.release()
                return False
            except Exception:
                os.close(fd)
                self._thread_lock.release()
                raise
            self._local.fd = fd
        self._local.depth = depth + 1
        return True

    def acquire_or_raise(self, message: str) -> None:
        if not self.acquire(blocking=False):
            raise LockBusyError(message)

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


class GenerationLock(InterProcessRLock):
    """Single-owner synthesis lock shared by web and CLI for one library root."""

    def __init__(self, library_root: Path):
        super().__init__(Path(library_root) / ".generation.lock")

    def try_acquire(self) -> bool:
        return self.acquire(blocking=False)

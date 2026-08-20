from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path


class LockBusyError(RuntimeError):
    """Raised when a requested non-blocking advisory lock is already owned."""


def _physical_lock_path(path: Path) -> Path:
    requested = Path(path)
    if requested.name in {".library.lock", ".generation.lock"}:
        kind = requested.name.strip(".")
        return requested.parent.parent / f".{requested.parent.name}.{kind}"
    return requested


class InterProcessRLock:
    """Thread-reentrant advisory lock for short library transactions."""

    def __init__(self, path: Path):
        self.path = _physical_lock_path(Path(path))
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
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
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


class GenerationLock:
    """Single-owner synthesis lease shared by web and CLI for one library root.

    Unlike the reentrant transaction lock, this lease stores its descriptor on
    the object so a request thread can reserve Metal before handing the lease to
    its worker thread for eventual release.
    """

    def __init__(self, library_root: Path):
        self.path = _physical_lock_path(Path(library_root) / ".generation.lock")
        self._fd: int | None = None
        self._guard = threading.Lock()

    def acquire(self, *, blocking: bool = True) -> bool:
        with self._guard:
            if self._fd is not None:
                return True
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                os.fchmod(fd, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                os.close(fd)
                return False
            except Exception:
                os.close(fd)
                raise
            self._fd = fd
            return True

    def try_acquire(self) -> bool:
        return self.acquire(blocking=False)

    def release(self) -> None:
        with self._guard:
            if self._fd is None:
                return
            fd = self._fd
            self._fd = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def __enter__(self) -> "GenerationLock":
        if not self.acquire():
            raise LockBusyError("generation lock is busy")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    @classmethod
    def is_locked(cls, library_root: Path) -> bool:
        probe = cls(library_root)
        if probe.try_acquire():
            probe.release()
            return False
        return True

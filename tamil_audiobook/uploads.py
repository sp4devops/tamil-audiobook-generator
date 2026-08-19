from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import UploadFile

BOOK_UPLOAD_LIMIT_BYTES = 100 * 1024 * 1024
VOICE_UPLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024


class UploadTooLargeError(ValueError):
    pass


async def save_upload_bounded(upload: UploadFile, *, suffix: str, limit_bytes: int) -> Path:
    """Stream an upload to a temp file while enforcing an actual byte limit."""
    if limit_bytes <= 0:
        raise ValueError("upload limit must be positive")

    total = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            temp_path = Path(handle.name)
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit_bytes:
                    raise UploadTooLargeError(f"upload exceeds {limit_bytes} byte limit")
                handle.write(chunk)
        return temp_path
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

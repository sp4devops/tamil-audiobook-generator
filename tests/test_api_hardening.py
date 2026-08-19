from __future__ import annotations

import asyncio
import io
import math
from pathlib import Path

import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from tamil_audiobook.api_models import PreferencesRequest, ProgressRequest, ResetRequest
from tamil_audiobook.uploads import UploadTooLargeError, save_upload_bounded


def test_progress_rejects_nonfinite_and_negative_values():
    for value in (math.inf, -math.inf, math.nan, -1.0):
        with pytest.raises(ValidationError):
            ProgressRequest(seconds=value, duration=10.0)
        with pytest.raises(ValidationError):
            ProgressRequest(seconds=1.0, duration=value)


def test_preferences_reject_unknown_and_invalid_values():
    with pytest.raises(ValidationError):
        PreferencesRequest(generation_mode="turbo")
    with pytest.raises(ValidationError):
        PreferencesRequest(playback_rate=9.0)
    with pytest.raises(ValidationError):
        PreferencesRequest.model_validate({"generation_mode": "cool", "mystery": True})


def test_reset_requires_exact_confirmation():
    assert ResetRequest(confirmation="DELETE ALL LOCAL DATA").confirmation == "DELETE ALL LOCAL DATA"
    with pytest.raises(ValidationError):
        ResetRequest(confirmation="delete all local data")


def test_bounded_upload_accepts_exact_limit_and_removes_oversize_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    exact = UploadFile(filename="book.txt", file=io.BytesIO(b"a" * 16))
    saved = asyncio.run(save_upload_bounded(exact, suffix=".txt", limit_bytes=16))
    try:
        assert saved.read_bytes() == b"a" * 16
    finally:
        saved.unlink(missing_ok=True)

    before = set(tmp_path.iterdir())
    oversized = UploadFile(filename="book.txt", file=io.BytesIO(b"b" * 17))
    with pytest.raises(UploadTooLargeError):
        asyncio.run(save_upload_bounded(oversized, suffix=".txt", limit_bytes=16))
    assert set(tmp_path.iterdir()) == before

from __future__ import annotations

import importlib
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi import HTTPException

from tamil_audiobook.api_models import ResetRequest
from tamil_audiobook.library import LocalLibrary


appmod = importlib.import_module("tamil_audiobook.app")


@pytest.fixture(autouse=True)
def isolated_jobs_and_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original_library = appmod.library
    with appmod._jobs_lock:
        appmod._jobs.clear()
    monkeypatch.setattr(appmod, "library", LocalLibrary(tmp_path / "library"))
    yield
    with appmod._jobs_lock:
        appmod._jobs.clear()
    appmod.library = original_library


def _make_book(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("வணக்கம் உலகம். This is a resource safety test.", encoding="utf-8")
    return appmod.library.import_book(source, title="Resource Test")


def _configure_fake_original_voice(tmp_path: Path) -> None:
    audio, transcript = appmod.library.voice_reference_paths()
    sf.write(audio, np.zeros(48000, dtype=np.float32), 24000)
    transcript.write_text("local reference transcript", encoding="utf-8")


def test_generation_mode_comes_from_persisted_cool_preference():
    assert appmod._generation_mode() == "cool"
    appmod.library.save_preferences({"generation_mode": "balanced"})
    assert appmod._generation_mode() == "balanced"


def test_different_book_generation_is_rejected_when_metal_slot_busy(tmp_path: Path):
    book = _make_book(tmp_path)
    _configure_fake_original_voice(tmp_path)
    with appmod._jobs_lock:
        appmod._jobs["busy"] = {
            "status": "running",
            "book_id": "other-book",
            "title": "Other Book",
            "_started_monotonic": time.monotonic(),
        }
    with pytest.raises(HTTPException) as exc:
        appmod.generate_book(book["id"])
    assert exc.value.status_code == 409
    assert "one Metal synthesis job" in str(exc.value.detail)


def test_destructive_operations_are_blocked_for_generating_book(tmp_path: Path):
    book = _make_book(tmp_path)
    with appmod._jobs_lock:
        appmod._jobs["busy"] = {
            "status": "running",
            "book_id": book["id"],
            "title": book["title"],
            "_started_monotonic": time.monotonic(),
        }
    with pytest.raises(HTTPException) as delete_exc:
        appmod.delete_book(book["id"])
    assert delete_exc.value.status_code == 409
    with pytest.raises(HTTPException) as clear_exc:
        appmod.clear_book_audio(book["id"])
    assert clear_exc.value.status_code == 409
    with pytest.raises(HTTPException) as reset_exc:
        appmod.reset(ResetRequest(confirmation="DELETE ALL LOCAL DATA"))
    assert reset_exc.value.status_code == 409


def test_terminal_job_history_is_bounded():
    for index in range(appmod._JOB_HISTORY_LIMIT + 20):
        appmod._job_update(
            f"job-{index}",
            status="completed",
            stage="ready",
            book_id=f"book-{index}",
        )
    with appmod._jobs_lock:
        terminal = [payload for payload in appmod._jobs.values() if payload.get("status") == "completed"]
    assert len(terminal) <= appmod._JOB_HISTORY_LIMIT


def test_dashboard_uses_single_state_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _make_book(tmp_path)
    _make_book(tmp_path)
    calls = 0
    original = appmod.library._state

    def counted_state():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(appmod.library, "_state", counted_state)
    dashboard = appmod.library.dashboard()
    assert len(dashboard["books"]) == 2
    assert calls == 1
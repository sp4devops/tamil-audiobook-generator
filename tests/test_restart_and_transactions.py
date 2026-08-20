from __future__ import annotations

import importlib
import json
import multiprocessing as mp
from pathlib import Path

from tamil_audiobook.library import LocalLibrary


def _create_playlist(root: str, name: str) -> None:
    LocalLibrary(Path(root)).create_playlist(name)


def test_concurrent_library_transactions_do_not_lose_playlist_updates(tmp_path: Path):
    root = tmp_path / "library"
    LocalLibrary(root)
    processes = [mp.Process(target=_create_playlist, args=(str(root), f"playlist-{index}")) for index in range(6)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=5)
        assert process.exitcode == 0

    lib = LocalLibrary(root)
    state = json.loads(lib.state_path.read_text(encoding="utf-8"))
    assert sorted(item["name"] for item in state["playlists"]) == [f"playlist-{index}" for index in range(6)]


def test_persisted_active_job_reconciles_to_interrupted_after_restart(tmp_path: Path, monkeypatch):
    app_module = importlib.import_module("tamil_audiobook.app")
    lib = LocalLibrary(tmp_path / "library")
    job_root = lib.root / "jobs"
    job_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(app_module, "library", lib)
    monkeypatch.setattr(app_module, "JOB_ROOT", job_root)
    app_module._jobs.clear()
    app_module._cancel_events.clear()

    job_id = "abc123def456"
    app_module._persist_job(
        job_id,
        {
            "status": "running",
            "stage": "synthesizing",
            "book_id": "book-does-not-need-to-exist",
            "title": "Interrupted Book",
            "playable_chunks": 4,
            "total_chunks": 10,
            "resumable": True,
        },
    )

    recovered = app_module._public_job(job_id)
    assert recovered["status"] == "interrupted"
    assert recovered["stage"] == "interrupted"
    assert recovered["resumable"] is True
    assert recovered["playable_chunks"] == 4
    assert "press Generate to resume" in recovered["error"]

    durable = json.loads((job_root / f"{job_id}.json").read_text(encoding="utf-8"))
    assert durable["status"] == "interrupted"


def test_web_and_cli_share_generation_lock_primitive():
    app_source = Path(__file__).parents[1] / "tamil_audiobook" / "app.py"
    cli_source = Path(__file__).parents[1] / "tamil_audiobook" / "cli.py"
    assert "GenerationLock(library.root)" in app_source.read_text(encoding="utf-8")
    assert "GenerationLock(lib.root)" in cli_source.read_text(encoding="utf-8")


def test_cancel_endpoint_is_exposed():
    app_module = importlib.import_module("tamil_audiobook.app")
    paths = {route.path for route in app_module.app.routes}
    assert "/api/jobs/{job_id}/cancel" in paths

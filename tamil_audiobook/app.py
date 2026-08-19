from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api_models import (
    BookEditRequest,
    FollowRequest,
    PlaylistCreateRequest,
    PlaylistUpdateRequest,
    PreferencesRequest,
    ProgressRequest,
    ResetRequest,
)
from .controlled_engine import synthesize_audiobook_with_controls
from .engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS, estimate_audiobook
from .generation_controls import OmniVoiceGenerationControls
from .library import LocalLibrary
from .uploads import BOOK_UPLOAD_LIMIT_BYTES, VOICE_UPLOAD_LIMIT_BYTES, UploadTooLargeError, save_upload_bounded
from .voice import ORIGINAL_REQUIRED_LABEL, ORIGINAL_SOURCE_LABEL, original_voice_available, resolve_voice

PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PACKAGE_ROOT / "static"

library = LocalLibrary()
app = FastAPI(title="Tamil Audiobook", docs_url="/api/docs", redoc_url=None)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_JOB_HISTORY_LIMIT = 32
_ACTIVE_STATUSES = {"queued", "running"}


def _prune_jobs_locked() -> None:
    terminal = [
        (job_id, float(payload.get("_finished_monotonic", 0.0)))
        for job_id, payload in _jobs.items()
        if payload.get("status") not in _ACTIVE_STATUSES
    ]
    terminal.sort(key=lambda item: item[1], reverse=True)
    for job_id, _ in terminal[_JOB_HISTORY_LIMIT:]:
        _jobs.pop(job_id, None)


def _job_update(job_id: str, **fields) -> None:
    with _jobs_lock:
        payload = _jobs.setdefault(job_id, {})
        payload.update(fields)
        if payload.get("status") not in _ACTIVE_STATUSES:
            payload.setdefault("_finished_monotonic", time.monotonic())
        _prune_jobs_locked()


def _public_payload(payload: dict) -> dict:
    public = dict(payload)
    started = public.pop("_started_monotonic", None)
    public.pop("_finished_monotonic", None)
    if started is not None and public.get("status") in _ACTIVE_STATUSES:
        public["elapsed_seconds"] = round(max(0.0, time.monotonic() - float(started)), 1)
    return public


def _public_job(job_id: str) -> dict:
    with _jobs_lock:
        payload = dict(_jobs.get(job_id, {}))
    if not payload:
        raise FileNotFoundError(job_id)
    return _public_payload(payload)


def _active_jobs_locked() -> list[tuple[str, dict]]:
    return [
        (job_id, payload)
        for job_id, payload in _jobs.items()
        if payload.get("status") in _ACTIVE_STATUSES
    ]


def _active_job_for_book(book_id: str) -> tuple[str, dict] | None:
    with _jobs_lock:
        candidates = [
            (job_id, dict(payload))
            for job_id, payload in _active_jobs_locked()
            if payload.get("book_id") == book_id
        ]
    if not candidates:
        return None
    job_id, payload = candidates[-1]
    return job_id, _public_payload(payload)


def _active_generation() -> tuple[str, dict] | None:
    with _jobs_lock:
        active = [(job_id, dict(payload)) for job_id, payload in _active_jobs_locked()]
    if not active:
        return None
    job_id, payload = active[-1]
    return job_id, _public_payload(payload)


def _ensure_generation_idle(action: str) -> None:
    active = _active_generation()
    if active:
        _, payload = active
        title = payload.get("title") or payload.get("book_id") or "another book"
        raise HTTPException(409, f"Cannot {action} while audiobook generation is running for {title}. Wait for it to finish first.")


def _voice_status() -> tuple[bool, str]:
    if original_voice_available(library):
        return True, ORIGINAL_SOURCE_LABEL
    return False, ORIGINAL_REQUIRED_LABEL


def _chunk_path(book_id: str, chunk_index: int) -> Path:
    if chunk_index < 0:
        raise FileNotFoundError(chunk_index)
    return library._book_dir(book_id) / "chunks" / f"chunk_{chunk_index:05d}.flac"


def _generation_mode() -> str:
    preferences = library._state().get("preferences", {})
    return str(preferences.get("generation_mode", "cool") or "cool")


def _generate(job_id: str, book_id: str, generation_mode: str) -> None:
    try:
        book = library.get_book(book_id)
        reference_audio, reference_text, voice_source = resolve_voice(library)
        book_dir = library._book_dir(book_id)
        wav = book_dir / "audiobook.wav"
        mp3 = book_dir / "audiobook.mp3"
        report_path = book_dir / "report.json"
        checkpoint_dir = book_dir / "chunks"

        def on_progress(payload: dict) -> None:
            _job_update(job_id, status="running", voice_source=voice_source, **payload)

        _job_update(
            job_id,
            status="running",
            stage="loading_model",
            percent=1.0,
            title=book["title"],
            voice_source=voice_source,
            generation_mode=generation_mode,
        )
        report = synthesize_audiobook_with_controls(
            controls=OmniVoiceGenerationControls(),
            text=library.text(book_id),
            reference_audio=reference_audio,
            reference_text=reference_text,
            output_wav=wav,
            output_mp3=mp3,
            num_steps=DEFAULT_NUM_STEPS,
            guidance_scale=DEFAULT_GUIDANCE_SCALE,
            report_path=report_path,
            progress_callback=on_progress,
            checkpoint_dir=checkpoint_dir,
            generation_mode=generation_mode,
        )
        cues = library.build_cues(book_id, report)
        wav.unlink(missing_ok=True)
        _job_update(
            job_id,
            status="completed",
            stage="ready",
            percent=100.0,
            completed_chunks=report["chunks"],
            playable_chunks=report["chunks"],
            total_chunks=report["chunks"],
            estimated_remaining_seconds=0.0,
            book_id=book_id,
            title=book["title"],
            voice_source=voice_source,
            generation_mode=report.get("generation_mode", generation_mode),
            audio_seconds=report["audio_seconds"],
            generation_seconds=report["generation_seconds"],
            aggregate_rtf=report["aggregate_rtf"],
            resumed_chunks=report.get("resumed_chunks", 0),
            cues=len(cues),
        )
    except Exception as exc:
        _job_update(job_id, status="failed", stage="failed", book_id=book_id, error=str(exc))


@app.get("/api/health")
def health() -> dict:
    ready, source = _voice_status()
    active = _active_generation()
    return {
        "status": "ok",
        "local_only": True,
        "voice_ready": ready,
        "voice_source": source,
        "generation_active": bool(active),
        "generation_mode": _generation_mode(),
    }


@app.get("/api/dashboard")
def dashboard() -> dict:
    payload = library.dashboard()
    ready, source = _voice_status()
    payload["voice_ready"] = ready
    payload["voice_source"] = source
    active = _active_generation()
    payload["generation"] = active[1] if active else None
    return payload


@app.get("/api/storage")
def storage() -> dict:
    return library.cache_stats()


@app.get("/api/books/{book_id}")
def book_detail(book_id: str) -> dict:
    try:
        book = library.get_book(book_id)
        book["text"] = library.text(book_id)
        book["cues"] = library.cues(book_id)
        report_path = library.report_path(book_id)
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            book["audio_seconds"] = float(report.get("audio_seconds", 0.0))
            book["generation_seconds"] = float(report.get("generation_seconds", 0.0))
            book["generation_mode"] = report.get("generation_mode")
        chunks_dir = library._book_dir(book_id) / "chunks"
        playable_chunks = 0
        while (chunks_dir / f"chunk_{playable_chunks:05d}.flac").is_file():
            playable_chunks += 1
        book["playable_chunks"] = playable_chunks
        book["estimate"] = estimate_audiobook(book["text"], generation_mode=_generation_mode())
        return book
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.get("/api/books/{book_id}/estimate")
def book_estimate(book_id: str) -> dict:
    try:
        return estimate_audiobook(library.text(book_id), generation_mode=_generation_mode())
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.patch("/api/books/{book_id}")
def edit_book(book_id: str, payload: BookEditRequest) -> dict:
    try:
        data = payload.model_dump(exclude_unset=True)
        return library.update_book(book_id, title=data.get("title"), author=data.get("author"), series=data.get("series"))
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/books/{book_id}")
def delete_book(book_id: str) -> dict:
    if _active_job_for_book(book_id):
        raise HTTPException(409, "Cannot delete a book while it is generating. Wait for generation to finish first.")
    try:
        return library.delete_book(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.delete("/api/books/{book_id}/audio")
def clear_book_audio(book_id: str) -> dict:
    if _active_job_for_book(book_id):
        raise HTTPException(409, "Cannot clear generated audio while this book is generating.")
    try:
        return library.delete_generated_audio(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.delete("/api/books/{book_id}/progress")
def clear_book_progress(book_id: str) -> dict:
    try:
        return library.clear_progress(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.post("/api/books/import")
async def import_book(file: UploadFile = File(...), title: str = Form(""), author: str = Form("Unknown author"), series: str = Form("")) -> dict:
    suffix = Path(file.filename or "book.txt").suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise HTTPException(400, "Only PDF, TXT and Markdown are supported")
    try:
        temp_path = await save_upload_bounded(file, suffix=suffix, limit_bytes=BOOK_UPLOAD_LIMIT_BYTES)
    except UploadTooLargeError:
        raise HTTPException(413, "Book upload is too large (maximum 100 MiB)")
    try:
        return library.import_book(temp_path, title=title or None, author=author, series=series)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/voice-reference")
async def save_voice_reference(audio: UploadFile = File(...), transcript: str = Form(...)) -> dict:
    _ensure_generation_idle("replace the voice reference")
    suffix = Path(audio.filename or "reference.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".opus", ".flac"}:
        raise HTTPException(400, "Unsupported reference audio format")
    if not transcript.strip():
        raise HTTPException(400, "Reference transcript is required")
    try:
        temp_path = await save_upload_bounded(audio, suffix=suffix, limit_bytes=VOICE_UPLOAD_LIMIT_BYTES)
    except UploadTooLargeError:
        raise HTTPException(413, "Voice reference is too large (maximum 50 MiB)")
    converted = temp_path.with_suffix(".normalized.wav")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(temp_path), "-vn", "-ac", "1", "-ar", "24000",
                "-c:a", "pcm_s16le", str(converted),
            ],
            check=True,
        )
        if not converted.is_file() or converted.stat().st_size < 1000:
            raise ValueError("Reference audio could not be normalized")
        target, _ = library.voice_reference_paths()
        library.save_voice_reference(converted, transcript)
        return {
            "status": "ok",
            "voice_ready": True,
            "voice_source": ORIGINAL_SOURCE_LABEL,
            "normalized_locally": True,
            "stored_locally": str(target),
        }
    except Exception as exc:
        raise HTTPException(400, str(exc))
    finally:
        temp_path.unlink(missing_ok=True)
        converted.unlink(missing_ok=True)


@app.delete("/api/voice-reference")
def delete_voice_reference() -> dict:
    _ensure_generation_idle("remove the voice reference")
    result = library.delete_voice_reference()
    result["voice_ready"] = False
    result["voice_source"] = ORIGINAL_REQUIRED_LABEL
    return result


@app.post("/api/books/{book_id}/generate")
def generate_book(book_id: str) -> dict:
    try:
        book = library.get_book(book_id)
        book_text = library.text(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    ready, source = _voice_status()
    if not ready:
        raise HTTPException(409, "Original source voice is required. Add the original recording and its exact transcript in Settings before generating.")

    generation_mode = _generation_mode()
    estimate = estimate_audiobook(book_text, generation_mode=generation_mode)
    started = time.monotonic()
    job_id = uuid.uuid4().hex[:12]
    initial = {
        "status": "queued",
        "stage": "queued",
        "book_id": book_id,
        "title": book["title"],
        "voice_source": source,
        "generation_mode": generation_mode,
        "percent": 0.0,
        "completed_chunks": 0,
        "playable_chunks": 0,
        "total_chunks": estimate["chunks"],
        "estimated_audio_seconds": estimate["audio_seconds"],
        "estimated_generation_seconds": estimate["generation_seconds"],
        "estimated_remaining_seconds": estimate["generation_seconds"],
        "elapsed_seconds": 0.0,
        "_started_monotonic": started,
    }

    with _jobs_lock:
        for existing_id, payload in _active_jobs_locked():
            if payload.get("book_id") == book_id:
                return {
                    "job_id": existing_id,
                    "status": payload["status"],
                    "estimate": estimate,
                    "voice_source": source,
                    "generation_mode": generation_mode,
                    "resumed_existing_job": True,
                }
            busy_title = payload.get("title") or payload.get("book_id") or "another book"
            raise HTTPException(
                409,
                f"Another audiobook is already generating ({busy_title}). ListenLeaf runs one Metal synthesis job at a time to protect memory and thermals.",
            )
        _jobs[job_id] = initial
        _prune_jobs_locked()

    threading.Thread(target=_generate, args=(job_id, book_id, generation_mode), daemon=True, name=f"listenleaf-{job_id}").start()
    return {
        "job_id": job_id,
        "status": "queued",
        "estimate": estimate,
        "voice_source": source,
        "generation_mode": generation_mode,
        "resumed_existing_job": False,
    }


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    try:
        return _public_job(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")


@app.get("/api/books/{book_id}/generation")
def book_generation(book_id: str) -> dict:
    try:
        library.get_book(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    active = _active_job_for_book(book_id)
    if not active:
        return {"active": False}
    job_id, payload = active
    return {"active": True, "job_id": job_id, **payload}


@app.get("/api/books/{book_id}/chunks/{chunk_index}")
def generated_chunk(book_id: str, chunk_index: int):
    try:
        library.get_book(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    path = _chunk_path(book_id, chunk_index)
    if not path.is_file():
        raise HTTPException(404, "Chunk is not available yet")
    return FileResponse(path, media_type="audio/flac", filename=path.name)


@app.get("/api/books/{book_id}/audio")
def audio(book_id: str):
    path = library.audio_path(book_id)
    if path.is_file():
        book = library.get_book(book_id)
        safe_title = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in book.get("title", "audiobook")).strip() or "audiobook"
        return FileResponse(path, media_type="audio/mpeg", filename=f"{safe_title}.mp3")
    preview = _chunk_path(book_id, 0)
    if preview.is_file():
        return FileResponse(preview, media_type="audio/flac", filename=f"{book_id}-preview.flac")
    raise HTTPException(404, "Audio has not been generated yet")


@app.post("/api/books/{book_id}/progress")
def progress(book_id: str, payload: ProgressRequest) -> dict:
    try:
        return library.update_progress(book_id, payload.seconds, payload.duration)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.delete("/api/progress")
def clear_all_progress() -> dict:
    return library.clear_progress()


@app.post("/api/preferences")
def preferences(payload: PreferencesRequest) -> dict:
    return library.save_preferences(payload.model_dump(exclude_none=True, exclude_unset=True))


@app.post("/api/playlists")
def create_playlist(payload: PlaylistCreateRequest) -> dict:
    try:
        return library.create_playlist(payload.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str) -> dict:
    try:
        return library.get_playlist(playlist_id)
    except FileNotFoundError:
        raise HTTPException(404, "Playlist not found")


@app.patch("/api/playlists/{playlist_id}")
def update_playlist(playlist_id: str, payload: PlaylistUpdateRequest) -> dict:
    try:
        data = payload.model_dump(exclude_unset=True)
        return library.update_playlist(playlist_id, name=data.get("name"), books=data.get("books"))
    except FileNotFoundError:
        raise HTTPException(404, "Playlist or book not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/playlists/{playlist_id}")
def delete_playlist(playlist_id: str) -> dict:
    try:
        return library.delete_playlist(playlist_id)
    except FileNotFoundError:
        raise HTTPException(404, "Playlist not found")


@app.post("/api/playlists/{playlist_id}/books/{book_id}")
def playlist_add(playlist_id: str, book_id: str) -> dict:
    try:
        return library.add_to_playlist(playlist_id, book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Playlist or book not found")


@app.delete("/api/playlists/{playlist_id}/books/{book_id}")
def playlist_remove(playlist_id: str, book_id: str) -> dict:
    try:
        return library.remove_from_playlist(playlist_id, book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Playlist not found")


@app.post("/api/follows")
def follow(payload: FollowRequest) -> dict:
    try:
        return library.set_follow(payload.kind, payload.value, payload.follow)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/activity")
def clear_activity() -> dict:
    return library.clear_activity()


@app.delete("/api/cache")
def clear_cache() -> dict:
    return library.clear_app_cache()


@app.post("/api/reset")
def reset(payload: ResetRequest) -> dict:
    _ensure_generation_idle("reset local data")
    try:
        return library.reset_local_data(payload.confirmation)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC_ROOT / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

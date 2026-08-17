from __future__ import annotations

import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS, estimate_audiobook, synthesize_audiobook
from .library import LocalLibrary
from .voice import ORIGINAL_REQUIRED_LABEL, ORIGINAL_SOURCE_LABEL, original_voice_available, resolve_voice

PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PACKAGE_ROOT / "static"

library = LocalLibrary()
app = FastAPI(title="Tamil Audiobook", docs_url="/api/docs", redoc_url=None)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _job_update(job_id: str, **fields) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(fields)


def _public_job(job_id: str) -> dict:
    with _jobs_lock:
        payload = dict(_jobs.get(job_id, {}))
    if not payload:
        raise FileNotFoundError(job_id)
    started = payload.pop("_started_monotonic", None)
    if started is not None and payload.get("status") in {"queued", "running"}:
        payload["elapsed_seconds"] = round(max(0.0, time.monotonic() - float(started)), 1)
    return payload


def _active_job_for_book(book_id: str) -> tuple[str, dict] | None:
    with _jobs_lock:
        candidates = [
            (job_id, dict(payload))
            for job_id, payload in _jobs.items()
            if payload.get("book_id") == book_id and payload.get("status") in {"queued", "running"}
        ]
    if not candidates:
        return None
    job_id, _ = candidates[-1]
    return job_id, _public_job(job_id)


def _voice_status() -> tuple[bool, str]:
    if original_voice_available(library):
        return True, ORIGINAL_SOURCE_LABEL
    return False, ORIGINAL_REQUIRED_LABEL


def _chunk_path(book_id: str, chunk_index: int) -> Path:
    if chunk_index < 0:
        raise FileNotFoundError(chunk_index)
    return library._book_dir(book_id) / "chunks" / f"chunk_{chunk_index:05d}.flac"


def _generate(job_id: str, book_id: str) -> None:
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

        _job_update(job_id, status="running", stage="loading_model", percent=1.0, voice_source=voice_source)
        report = synthesize_audiobook(
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
            audio_seconds=report["audio_seconds"],
            generation_seconds=report["generation_seconds"],
            aggregate_rtf=report["aggregate_rtf"],
            resumed_chunks=report.get("resumed_chunks", 0),
            cues=len(cues),
        )
    except Exception as exc:
        _job_update(job_id, status="failed", stage="failed", error=str(exc))


@app.get("/api/health")
def health() -> dict:
    ready, source = _voice_status()
    return {"status": "ok", "local_only": True, "voice_ready": ready, "voice_source": source}


@app.get("/api/dashboard")
def dashboard() -> dict:
    payload = library.dashboard()
    ready, source = _voice_status()
    payload["voice_ready"] = ready
    payload["voice_source"] = source
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
            import json
            report = json.loads(report_path.read_text(encoding="utf-8"))
            book["audio_seconds"] = float(report.get("audio_seconds", 0.0))
            book["generation_seconds"] = float(report.get("generation_seconds", 0.0))
        chunks_dir = library._book_dir(book_id) / "chunks"
        playable_chunks = 0
        while (chunks_dir / f"chunk_{playable_chunks:05d}.flac").is_file():
            playable_chunks += 1
        book["playable_chunks"] = playable_chunks
        book["estimate"] = estimate_audiobook(book["text"])
        return book
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.get("/api/books/{book_id}/estimate")
def book_estimate(book_id: str) -> dict:
    try:
        return estimate_audiobook(library.text(book_id))
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.patch("/api/books/{book_id}")
def edit_book(book_id: str, payload: dict) -> dict:
    try:
        return library.update_book(book_id, title=payload.get("title"), author=payload.get("author"), series=payload.get("series"))
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/books/{book_id}")
def delete_book(book_id: str) -> dict:
    try:
        return library.delete_book(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.delete("/api/books/{book_id}/audio")
def clear_book_audio(book_id: str) -> dict:
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
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        temp_path = Path(handle.name)
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)
    try:
        return library.import_book(temp_path, title=title or None, author=author, series=series)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/voice-reference")
async def save_voice_reference(audio: UploadFile = File(...), transcript: str = Form(...)) -> dict:
    suffix = Path(audio.filename or "reference.wav").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".opus", ".flac"}:
        raise HTTPException(400, "Unsupported reference audio format")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        temp_path = Path(handle.name)
        while chunk := await audio.read(1024 * 1024):
            handle.write(chunk)
    try:
        target, _ = library.voice_reference_paths()
        if suffix == ".wav":
            library.save_voice_reference(temp_path, transcript)
        else:
            converted = temp_path.with_suffix(".converted.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(temp_path), "-ac", "1", "-ar", "24000", str(converted)],
                check=True,
            )
            library.save_voice_reference(converted, transcript)
            converted.unlink(missing_ok=True)
        return {"status": "ok", "voice_ready": True, "voice_source": ORIGINAL_SOURCE_LABEL, "stored_locally": str(target)}
    except Exception as exc:
        raise HTTPException(400, str(exc))
    finally:
        temp_path.unlink(missing_ok=True)


@app.delete("/api/voice-reference")
def delete_voice_reference() -> dict:
    result = library.delete_voice_reference()
    result["voice_ready"] = False
    result["voice_source"] = ORIGINAL_REQUIRED_LABEL
    return result


@app.post("/api/books/{book_id}/generate")
def generate_book(book_id: str) -> dict:
    try:
        book_text = library.text(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    ready, source = _voice_status()
    if not ready:
        raise HTTPException(409, "Original source voice is required. Add the original recording and its exact transcript in Settings before generating.")

    active = _active_job_for_book(book_id)
    if active:
        job_id, payload = active
        return {"job_id": job_id, "status": payload["status"], "estimate": estimate_audiobook(book_text), "voice_source": source, "resumed_existing_job": True}

    estimate = estimate_audiobook(book_text)
    job_id = uuid.uuid4().hex[:12]
    _job_update(
        job_id,
        status="queued",
        stage="queued",
        book_id=book_id,
        voice_source=source,
        percent=0.0,
        completed_chunks=0,
        playable_chunks=0,
        total_chunks=estimate["chunks"],
        estimated_audio_seconds=estimate["audio_seconds"],
        estimated_generation_seconds=estimate["generation_seconds"],
        estimated_remaining_seconds=estimate["generation_seconds"],
        elapsed_seconds=0.0,
        _started_monotonic=time.monotonic(),
    )
    threading.Thread(target=_generate, args=(job_id, book_id), daemon=True).start()
    return {"job_id": job_id, "status": "queued", "estimate": estimate, "voice_source": source, "resumed_existing_job": False}


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
        return FileResponse(path, media_type="audio/mpeg", filename=f"{book_id}.mp3")
    preview = _chunk_path(book_id, 0)
    if preview.is_file():
        return FileResponse(preview, media_type="audio/flac", filename=f"{book_id}-preview.flac")
    raise HTTPException(404, "Audio has not been generated yet")


@app.post("/api/books/{book_id}/progress")
def progress(book_id: str, payload: dict) -> dict:
    try:
        return library.update_progress(book_id, payload.get("seconds", 0), payload.get("duration", 0))
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")


@app.delete("/api/progress")
def clear_all_progress() -> dict:
    return library.clear_progress()


@app.post("/api/preferences")
def preferences(payload: dict) -> dict:
    return library.save_preferences(payload)


@app.post("/api/playlists")
def create_playlist(payload: dict) -> dict:
    try:
        return library.create_playlist(str(payload.get("name", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/playlists/{playlist_id}")
def get_playlist(playlist_id: str) -> dict:
    try:
        return library.get_playlist(playlist_id)
    except FileNotFoundError:
        raise HTTPException(404, "Playlist not found")


@app.patch("/api/playlists/{playlist_id}")
def update_playlist(playlist_id: str, payload: dict) -> dict:
    try:
        return library.update_playlist(playlist_id, name=payload.get("name"), books=payload.get("books"))
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
def follow(payload: dict) -> dict:
    try:
        return library.set_follow(str(payload.get("kind", "")), str(payload.get("value", "")), bool(payload.get("follow", True)))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/activity")
def clear_activity() -> dict:
    return library.clear_activity()


@app.delete("/api/cache")
def clear_cache() -> dict:
    return library.clear_app_cache()


@app.post("/api/reset")
def reset(payload: dict) -> dict:
    try:
        return library.reset_local_data(str(payload.get("confirmation", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/")
def index():
    return FileResponse(STATIC_ROOT / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
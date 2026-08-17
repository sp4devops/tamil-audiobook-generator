from __future__ import annotations

import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS, synthesize_audiobook
from .library import LocalLibrary

PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PACKAGE_ROOT / "static"

library = LocalLibrary()
app = FastAPI(title="Tamil Audiobook", docs_url="/api/docs", redoc_url=None)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _job_update(job_id: str, **fields) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(fields)


def _generate(job_id: str, book_id: str) -> None:
    try:
        book = library.get_book(book_id)
        reference_audio, reference_text_path = library.voice_reference_paths()
        if not library.voice_ready():
            raise RuntimeError("Voice reference is not configured")
        book_dir = library._book_dir(book_id)
        wav = book_dir / "audiobook.wav"
        mp3 = book_dir / "audiobook.mp3"
        report_path = book_dir / "report.json"
        _job_update(job_id, status="running", stage="synthesizing")
        report = synthesize_audiobook(
            text=library.text(book_id),
            reference_audio=reference_audio,
            reference_text=reference_text_path.read_text(encoding="utf-8").strip(),
            output_wav=wav,
            output_mp3=mp3,
            num_steps=DEFAULT_NUM_STEPS,
            guidance_scale=DEFAULT_GUIDANCE_SCALE,
            report_path=report_path,
        )
        cues = library.build_cues(book_id, report)
        wav.unlink(missing_ok=True)
        _job_update(job_id, status="completed", stage="ready", book_id=book_id, title=book["title"], audio_seconds=report["audio_seconds"], aggregate_rtf=report["aggregate_rtf"], cues=len(cues))
    except Exception as exc:
        _job_update(job_id, status="failed", stage="failed", error=str(exc))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "local_only": True, "voice_ready": library.voice_ready()}


@app.get("/api/dashboard")
def dashboard() -> dict:
    return library.dashboard()


@app.get("/api/storage")
def storage() -> dict:
    return library.cache_stats()


@app.get("/api/books/{book_id}")
def book_detail(book_id: str) -> dict:
    try:
        book = library.get_book(book_id)
        book["text"] = library.text(book_id)
        book["cues"] = library.cues(book_id)
        return book
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
            import subprocess
            converted = temp_path.with_suffix(".converted.wav")
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(temp_path), "-ac", "1", "-ar", "24000", str(converted)], check=True)
            library.save_voice_reference(converted, transcript)
            converted.unlink(missing_ok=True)
        return {"status": "ok", "voice_ready": library.voice_ready(), "stored_locally": str(target)}
    except Exception as exc:
        raise HTTPException(400, str(exc))
    finally:
        temp_path.unlink(missing_ok=True)


@app.delete("/api/voice-reference")
def delete_voice_reference() -> dict:
    return library.delete_voice_reference()


@app.post("/api/books/{book_id}/generate")
def generate_book(book_id: str) -> dict:
    try:
        library.get_book(book_id)
    except FileNotFoundError:
        raise HTTPException(404, "Book not found")
    if not library.voice_ready():
        raise HTTPException(409, "Configure the local voice reference first")
    job_id = uuid.uuid4().hex[:12]
    _job_update(job_id, status="queued", stage="queued", book_id=book_id)
    threading.Thread(target=_generate, args=(job_id, book_id), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    with _jobs_lock:
        payload = dict(_jobs.get(job_id, {}))
    if not payload:
        raise HTTPException(404, "Job not found")
    return payload


@app.get("/api/books/{book_id}/audio")
def audio(book_id: str):
    path = library.audio_path(book_id)
    if not path.is_file():
        raise HTTPException(404, "Audio has not been generated")
    return FileResponse(path, media_type="audio/mpeg", filename=f"{book_id}.mp3")


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

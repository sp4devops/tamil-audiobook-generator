from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .engine import chunk_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_library_root() -> Path:
    return Path(os.environ.get("TAMIL_AUDIOBOOK_HOME", "~/.tamil_audiobook")).expanduser()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def extract_book_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        return "\n\n".join(page for page in pages if page).strip()
    raise ValueError("Supported book formats are PDF, TXT, and Markdown")


class LocalLibrary:
    """Persistent, local-only book library stored below ~/.tamil_audiobook by default."""

    def __init__(self, root: Path | None = None):
        self.root = (root or default_library_root()).expanduser().resolve()
        self.books_root = self.root / "books"
        self.private_root = self.root / "private"
        self.state_path = self.root / "state.json"
        self.books_root.mkdir(parents=True, exist_ok=True)
        self.private_root.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self._write_state(self._default_state())

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "progress": {},
            "playlists": [],
            "follows": {"authors": [], "series": []},
            "activity": [],
            "preferences": {
                "playback_rate": 1.0,
                "focus_mode": False,
                "focus_minutes": 25,
                "break_minutes": 5,
                "reduce_motion": False,
                "large_text": False,
                "eq_preset": "flat",
                "ambience": "off",
            },
        }

    def _state(self) -> dict[str, Any]:
        state = _read_json(self.state_path, self._default_state())
        defaults = self._default_state()
        for key, value in defaults.items():
            state.setdefault(key, value)
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        _atomic_json(self.state_path, state)

    def _book_dir(self, book_id: str) -> Path:
        path = (self.books_root / book_id).resolve()
        if path.parent != self.books_root.resolve():
            raise ValueError("invalid book id")
        return path

    def import_book(
        self,
        source: Path,
        *,
        title: str | None = None,
        author: str = "Unknown author",
        series: str = "",
    ) -> dict[str, Any]:
        text = extract_book_text(source)
        if not text:
            raise ValueError("No readable text was found in the book")
        book_id = uuid.uuid4().hex[:12]
        book_dir = self._book_dir(book_id)
        book_dir.mkdir(parents=True)
        source_target = book_dir / ("source" + source.suffix.lower())
        shutil.copy2(source, source_target)
        (book_dir / "text.txt").write_text(text, encoding="utf-8")
        now = _now()
        meta = {
            "id": book_id,
            "title": (title or source.stem).strip() or "Untitled",
            "author": author.strip() or "Unknown author",
            "series": series.strip(),
            "source_format": source.suffix.lower().lstrip("."),
            "characters": len(text),
            "words": len(text.split()),
            "created_at": now,
            "updated_at": now,
        }
        _atomic_json(book_dir / "metadata.json", meta)
        self._add_activity("import", book_id, meta["title"])
        return self.get_book(book_id)

    def list_books(self) -> list[dict[str, Any]]:
        books = []
        for item in self.books_root.iterdir():
            if not item.is_dir():
                continue
            meta = _read_json(item / "metadata.json", None)
            if not meta:
                continue
            books.append(self._decorate(meta))
        return sorted(books, key=lambda book: book.get("updated_at", ""), reverse=True)

    def get_book(self, book_id: str) -> dict[str, Any]:
        book_dir = self._book_dir(book_id)
        meta = _read_json(book_dir / "metadata.json", None)
        if not meta:
            raise FileNotFoundError(book_id)
        return self._decorate(meta)

    def _decorate(self, meta: dict[str, Any]) -> dict[str, Any]:
        book_dir = self._book_dir(meta["id"])
        state = self._state()
        result = dict(meta)
        result["has_audio"] = (book_dir / "audiobook.mp3").is_file()
        result["has_cues"] = (book_dir / "cues.json").is_file()
        result["progress"] = state["progress"].get(meta["id"], {"seconds": 0.0, "duration": 0.0})
        return result

    def text(self, book_id: str) -> str:
        return (self._book_dir(book_id) / "text.txt").read_text(encoding="utf-8")

    def audio_path(self, book_id: str) -> Path:
        return self._book_dir(book_id) / "audiobook.mp3"

    def report_path(self, book_id: str) -> Path:
        return self._book_dir(book_id) / "report.json"

    def cues(self, book_id: str) -> list[dict[str, Any]]:
        return _read_json(self._book_dir(book_id) / "cues.json", [])

    def build_cues(self, book_id: str, report: dict[str, Any]) -> list[dict[str, Any]]:
        chunks = chunk_text(self.text(book_id))
        chunk_reports = report.get("chunk_reports", [])
        if len(chunks) != len(chunk_reports):
            raise RuntimeError("generated chunk count does not match source text chunks")
        fade = float(report.get("crossfade_ms", 0)) / 1000.0
        cursor = 0.0
        cues: list[dict[str, Any]] = []
        for index, (chunk, timing) in enumerate(zip(chunks, chunk_reports)):
            duration = float(timing["audio_seconds"])
            end = cursor + duration
            cues.append({
                "index": index,
                "start": round(cursor, 3),
                "end": round(end, 3),
                "text": chunk.text,
                "language": chunk.language,
            })
            cursor = max(cursor, end - fade)
        _atomic_json(self._book_dir(book_id) / "cues.json", cues)
        return cues

    def voice_reference_paths(self) -> tuple[Path, Path]:
        return self.private_root / "voice_reference.wav", self.private_root / "voice_reference.txt"

    def save_voice_reference(self, audio: Path, transcript: str) -> None:
        if not transcript.strip():
            raise ValueError("reference transcript is required")
        audio_target, text_target = self.voice_reference_paths()
        shutil.copy2(audio, audio_target)
        text_target.write_text(transcript.strip(), encoding="utf-8")

    def voice_ready(self) -> bool:
        audio, text = self.voice_reference_paths()
        return audio.is_file() and text.is_file() and bool(text.read_text(encoding="utf-8").strip())

    def update_progress(self, book_id: str, seconds: float, duration: float) -> dict[str, Any]:
        self.get_book(book_id)
        state = self._state()
        entry = {
            "seconds": max(0.0, float(seconds)),
            "duration": max(0.0, float(duration)),
            "updated_at": _now(),
        }
        state["progress"][book_id] = entry
        self._write_state(state)
        return entry

    def save_preferences(self, preferences: dict[str, Any]) -> dict[str, Any]:
        state = self._state()
        state["preferences"].update(preferences)
        self._write_state(state)
        return state["preferences"]

    def create_playlist(self, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("playlist name is required")
        state = self._state()
        playlist = {"id": uuid.uuid4().hex[:10], "name": name, "books": [], "created_at": _now()}
        state["playlists"].append(playlist)
        self._write_state(state)
        return playlist

    def add_to_playlist(self, playlist_id: str, book_id: str) -> dict[str, Any]:
        self.get_book(book_id)
        state = self._state()
        for playlist in state["playlists"]:
            if playlist["id"] == playlist_id:
                if book_id not in playlist["books"]:
                    playlist["books"].append(book_id)
                self._write_state(state)
                return playlist
        raise FileNotFoundError(playlist_id)

    def set_follow(self, kind: str, value: str, follow: bool) -> dict[str, Any]:
        if kind not in {"authors", "series"}:
            raise ValueError("follow kind must be authors or series")
        value = value.strip()
        state = self._state()
        values = state["follows"][kind]
        if follow and value and value not in values:
            values.append(value)
        if not follow and value in values:
            values.remove(value)
        self._write_state(state)
        return state["follows"]

    def dashboard(self) -> dict[str, Any]:
        state = self._state()
        books = self.list_books()
        continue_listening = [book for book in books if book["progress"].get("seconds", 0) > 0]
        continue_listening.sort(key=lambda b: b["progress"].get("updated_at", ""), reverse=True)
        return {
            "books": books,
            "continue_listening": continue_listening[:8],
            "playlists": state["playlists"],
            "follows": state["follows"],
            "activity": state["activity"][:30],
            "preferences": state["preferences"],
            "voice_ready": self.voice_ready(),
        }

    def _add_activity(self, action: str, book_id: str, title: str) -> None:
        state = self._state()
        state["activity"].insert(0, {"action": action, "book_id": book_id, "title": title, "at": _now()})
        state["activity"] = state["activity"][:100]
        self._write_state(state)

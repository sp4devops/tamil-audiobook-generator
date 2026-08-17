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


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


class LocalLibrary:
    """Persistent, local-only book library stored below ~/.tamil_audiobook by default."""

    def __init__(self, root: Path | None = None):
        self.root = (root or default_library_root()).expanduser().resolve()
        self.books_root = self.root / "books"
        self.private_root = self.root / "private"
        self.cache_root = self.root / "cache"
        self.state_path = self.root / "state.json"
        self.books_root.mkdir(parents=True, exist_ok=True)
        self.private_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
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
                "theme": "midnight",
                "repeat_mode": "off",
                "shuffle": False,
                "skip_seconds": 15,
            },
        }

    def _state(self) -> dict[str, Any]:
        state = _read_json(self.state_path, self._default_state())
        defaults = self._default_state()
        for key, value in defaults.items():
            if key not in state:
                state[key] = value
            elif isinstance(value, dict) and isinstance(state[key], dict):
                for nested_key, nested_value in value.items():
                    state[key].setdefault(nested_key, nested_value)
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

    def update_book(self, book_id: str, *, title: str | None = None, author: str | None = None, series: str | None = None) -> dict[str, Any]:
        book_dir = self._book_dir(book_id)
        meta = _read_json(book_dir / "metadata.json", None)
        if not meta:
            raise FileNotFoundError(book_id)
        if title is not None:
            value = title.strip()
            if not value:
                raise ValueError("book title cannot be empty")
            meta["title"] = value
        if author is not None:
            meta["author"] = author.strip() or "Unknown author"
        if series is not None:
            meta["series"] = series.strip()
        meta["updated_at"] = _now()
        _atomic_json(book_dir / "metadata.json", meta)
        self._add_activity("edit", book_id, meta["title"])
        return self.get_book(book_id)

    def delete_book(self, book_id: str) -> dict[str, Any]:
        book = self.get_book(book_id)
        book_dir = self._book_dir(book_id)
        shutil.rmtree(book_dir)
        state = self._state()
        state["progress"].pop(book_id, None)
        for playlist in state["playlists"]:
            playlist["books"] = [item for item in playlist["books"] if item != book_id]
            playlist["updated_at"] = _now()
        self._write_state(state)
        self._add_activity("delete", book_id, book["title"])
        return {"status": "deleted", "book_id": book_id, "title": book["title"]}

    def _decorate(self, meta: dict[str, Any]) -> dict[str, Any]:
        book_dir = self._book_dir(meta["id"])
        state = self._state()
        result = dict(meta)
        result["has_audio"] = (book_dir / "audiobook.mp3").is_file()
        result["has_cues"] = (book_dir / "cues.json").is_file()
        result["audio_bytes"] = (book_dir / "audiobook.mp3").stat().st_size if result["has_audio"] else 0
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

    def delete_generated_audio(self, book_id: str) -> dict[str, Any]:
        self.get_book(book_id)
        book_dir = self._book_dir(book_id)
        removed = []
        for name in ("audiobook.mp3", "audiobook.wav", "report.json", "cues.json"):
            path = book_dir / name
            if path.exists():
                path.unlink()
                removed.append(name)
        state = self._state()
        state["progress"].pop(book_id, None)
        self._write_state(state)
        return {"status": "cleared", "book_id": book_id, "removed": removed}

    def voice_reference_paths(self) -> tuple[Path, Path]:
        return self.private_root / "voice_reference.wav", self.private_root / "voice_reference.txt"

    def save_voice_reference(self, audio: Path, transcript: str) -> None:
        if not transcript.strip():
            raise ValueError("reference transcript is required")
        audio_target, text_target = self.voice_reference_paths()
        shutil.copy2(audio, audio_target)
        text_target.write_text(transcript.strip(), encoding="utf-8")

    def delete_voice_reference(self) -> dict[str, Any]:
        audio, text = self.voice_reference_paths()
        removed = []
        for path in (audio, text):
            if path.exists():
                path.unlink()
                removed.append(path.name)
        return {"status": "cleared", "removed": removed}

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

    def clear_progress(self, book_id: str | None = None) -> dict[str, Any]:
        state = self._state()
        if book_id is None:
            count = len(state["progress"])
            state["progress"] = {}
        else:
            self.get_book(book_id)
            count = int(book_id in state["progress"])
            state["progress"].pop(book_id, None)
        self._write_state(state)
        return {"status": "cleared", "entries": count}

    def save_preferences(self, preferences: dict[str, Any]) -> dict[str, Any]:
        state = self._state()
        allowed = set(self._default_state()["preferences"])
        for key, value in preferences.items():
            if key in allowed:
                state["preferences"][key] = value
        self._write_state(state)
        return state["preferences"]

    def create_playlist(self, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("playlist name is required")
        state = self._state()
        now = _now()
        playlist = {"id": uuid.uuid4().hex[:10], "name": name, "books": [], "created_at": now, "updated_at": now}
        state["playlists"].append(playlist)
        self._write_state(state)
        return playlist

    def get_playlist(self, playlist_id: str) -> dict[str, Any]:
        state = self._state()
        for playlist in state["playlists"]:
            if playlist["id"] == playlist_id:
                return dict(playlist)
        raise FileNotFoundError(playlist_id)

    def update_playlist(self, playlist_id: str, *, name: str | None = None, books: list[str] | None = None) -> dict[str, Any]:
        state = self._state()
        for playlist in state["playlists"]:
            if playlist["id"] != playlist_id:
                continue
            if name is not None:
                clean = name.strip()
                if not clean:
                    raise ValueError("playlist name is required")
                playlist["name"] = clean
            if books is not None:
                normalized = []
                for book_id in books:
                    self.get_book(book_id)
                    if book_id not in normalized:
                        normalized.append(book_id)
                playlist["books"] = normalized
            playlist["updated_at"] = _now()
            self._write_state(state)
            return dict(playlist)
        raise FileNotFoundError(playlist_id)

    def delete_playlist(self, playlist_id: str) -> dict[str, Any]:
        state = self._state()
        before = len(state["playlists"])
        state["playlists"] = [playlist for playlist in state["playlists"] if playlist["id"] != playlist_id]
        if len(state["playlists"]) == before:
            raise FileNotFoundError(playlist_id)
        self._write_state(state)
        return {"status": "deleted", "playlist_id": playlist_id}

    def add_to_playlist(self, playlist_id: str, book_id: str) -> dict[str, Any]:
        self.get_book(book_id)
        playlist = self.get_playlist(playlist_id)
        books = list(playlist["books"])
        if book_id not in books:
            books.append(book_id)
        return self.update_playlist(playlist_id, books=books)

    def remove_from_playlist(self, playlist_id: str, book_id: str) -> dict[str, Any]:
        playlist = self.get_playlist(playlist_id)
        books = [item for item in playlist["books"] if item != book_id]
        return self.update_playlist(playlist_id, books=books)

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

    def clear_activity(self) -> dict[str, Any]:
        state = self._state()
        count = len(state["activity"])
        state["activity"] = []
        self._write_state(state)
        return {"status": "cleared", "entries": count}

    def cache_stats(self) -> dict[str, Any]:
        generated_bytes = 0
        generated_books = 0
        for item in self.books_root.iterdir():
            if not item.is_dir():
                continue
            audio = item / "audiobook.mp3"
            report = item / "report.json"
            cues = item / "cues.json"
            if audio.exists():
                generated_books += 1
            for path in (audio, report, cues, item / "audiobook.wav"):
                if path.exists():
                    generated_bytes += path.stat().st_size
        return {
            "app_cache_bytes": _dir_size(self.cache_root),
            "generated_bytes": generated_bytes,
            "generated_books": generated_books,
            "library_bytes": _dir_size(self.root),
        }

    def clear_app_cache(self) -> dict[str, Any]:
        before = _dir_size(self.cache_root)
        shutil.rmtree(self.cache_root, ignore_errors=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        return {"status": "cleared", "bytes_removed": before}

    def reset_local_data(self, confirmation: str) -> dict[str, Any]:
        if confirmation != "DELETE ALL LOCAL DATA":
            raise ValueError("confirmation phrase does not match")
        shutil.rmtree(self.root, ignore_errors=True)
        self.books_root.mkdir(parents=True, exist_ok=True)
        self.private_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._write_state(self._default_state())
        return {"status": "reset", "root": str(self.root)}

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
            "storage": self.cache_stats(),
        }

    def _add_activity(self, action: str, book_id: str, title: str) -> None:
        state = self._state()
        state["activity"].insert(0, {"action": action, "book_id": book_id, "title": title, "at": _now()})
        state["activity"] = state["activity"][:100]
        self._write_state(state)

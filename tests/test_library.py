from pathlib import Path

from tamil_audiobook.library import LocalLibrary, extract_book_text
from tamil_audiobook.textnorm import normalize_book_text


def make_book(tmp_path: Path, lib: LocalLibrary, name: str = "book"):
    source = tmp_path / f"{name}.txt"
    source.write_text("வணக்கம் உலகம். This is a local audiobook test.", encoding="utf-8")
    return lib.import_book(source, title="Test Book", author="Test Author", series="Test Series")


def test_txt_import_library_state_and_playlist(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    book = make_book(tmp_path, lib)
    assert book["title"] == "Test Book"
    assert book["author"] == "Test Author"
    assert lib.text(book["id"]).startswith("வணக்கம்")
    assert not book["has_audio"]
    progress = lib.update_progress(book["id"], 12.5, 100)
    assert progress["seconds"] == 12.5
    playlist = lib.create_playlist("Focus reads")
    updated = lib.add_to_playlist(playlist["id"], book["id"])
    assert book["id"] in updated["books"]
    follows = lib.set_follow("authors", "Test Author", True)
    assert "Test Author" in follows["authors"]


def test_tamil_visual_order_pdf_damage_is_repaired():
    # Typical PDF extraction puts the visible left-side vowel glyph before the
    # consonant. The browser then shows an orphan/dotted sign and TTS receives
    # the wrong logical order.
    damaged = "ேநயர்கேள, வணக்கம். ெகாடுத்த ேகாப்பு"
    repaired = normalize_book_text(damaged)
    assert repaired.startswith("நேயர்கேள")
    assert "கொடுத்த" in repaired
    assert "கோப்பு" in repaired
    assert "◌" not in repaired


def test_existing_import_is_repaired_on_read(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    book = make_book(tmp_path, lib)
    text_path = lib._book_dir(book["id"]) / "text.txt"
    text_path.write_text("ேநயர்கேள", encoding="utf-8")
    assert lib.text(book["id"]) == "நேயர்கேள"
    assert text_path.read_text(encoding="utf-8") == "நேயர்கேள"


def test_playlist_full_crud_and_membership(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    first = make_book(tmp_path, lib, "one")
    second = make_book(tmp_path, lib, "two")
    playlist = lib.create_playlist("Original")
    playlist = lib.update_playlist(playlist["id"], name="Renamed", books=[first["id"], second["id"]])
    assert playlist["name"] == "Renamed"
    assert playlist["books"] == [first["id"], second["id"]]
    playlist = lib.remove_from_playlist(playlist["id"], first["id"])
    assert playlist["books"] == [second["id"]]
    deleted = lib.delete_playlist(playlist["id"])
    assert deleted["status"] == "deleted"
    assert lib.dashboard()["playlists"] == []


def test_book_edit_delete_and_playlist_cleanup(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    book = make_book(tmp_path, lib)
    playlist = lib.create_playlist("Keep")
    lib.add_to_playlist(playlist["id"], book["id"])
    edited = lib.update_book(book["id"], title="Edited", author="New Author", series="New Series")
    assert edited["title"] == "Edited"
    assert edited["author"] == "New Author"
    lib.update_progress(book["id"], 20, 50)
    result = lib.delete_book(book["id"])
    assert result["status"] == "deleted"
    assert not lib._book_dir(book["id"]).exists()
    assert lib.get_playlist(playlist["id"])["books"] == []
    assert book["id"] not in lib._state()["progress"]


def test_generated_audio_cleanup_and_cache_stats(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    book = make_book(tmp_path, lib)
    book_dir = lib._book_dir(book["id"])
    (book_dir / "audiobook.mp3").write_bytes(b"audio" * 100)
    (book_dir / "report.json").write_text("{}", encoding="utf-8")
    (book_dir / "cues.json").write_text("[]", encoding="utf-8")
    chunks = book_dir / "chunks"
    chunks.mkdir()
    (chunks / "chunk_00000.flac").write_bytes(b"chunk")
    lib.update_progress(book["id"], 1, 2)
    stats = lib.cache_stats()
    assert stats["generated_books"] == 1
    assert stats["generated_bytes"] > 0
    result = lib.delete_generated_audio(book["id"])
    assert "audiobook.mp3" in result["removed"]
    assert "chunks" in result["removed"]
    assert not (book_dir / "audiobook.mp3").exists()
    assert not chunks.exists()
    assert book["id"] not in lib._state()["progress"]


def test_theme_preferences_and_reset_guard(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    make_book(tmp_path, lib)
    prefs = lib.save_preferences({"theme": "paper", "repeat_mode": "one", "shuffle": True, "skip_seconds": 30, "ignored": "x"})
    assert prefs["theme"] == "paper"
    assert prefs["repeat_mode"] == "one"
    assert prefs["shuffle"] is True
    assert prefs["skip_seconds"] == 30
    assert "ignored" not in prefs
    try:
        lib.reset_local_data("wrong")
    except ValueError:
        pass
    else:
        raise AssertionError("reset must require exact confirmation phrase")
    assert lib.list_books()
    result = lib.reset_local_data("DELETE ALL LOCAL DATA")
    assert result["status"] == "reset"
    assert lib.list_books() == []
    assert lib.dashboard()["preferences"]["theme"] == "midnight"


def test_cache_activity_progress_and_voice_deletion(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    book = make_book(tmp_path, lib)
    lib.update_progress(book["id"], 2, 10)
    (lib.cache_root / "temp.bin").write_bytes(b"x" * 100)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"fake")
    lib.save_voice_reference(audio, "test transcript")
    assert lib.voice_ready()
    assert lib.clear_app_cache()["bytes_removed"] == 100
    assert lib.clear_progress()["entries"] == 1
    assert lib.clear_activity()["entries"] >= 1
    assert lib.delete_voice_reference()["status"] == "cleared"
    assert not lib.voice_ready()


def test_build_cues_tracks_crossfade(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("First sentence. Second sentence. Third sentence.", encoding="utf-8")
    lib = LocalLibrary(tmp_path / "library")
    book = lib.import_book(source)
    from tamil_audiobook.engine import chunk_text
    chunks = chunk_text(lib.text(book["id"]))
    report = {"crossfade_ms": 55, "chunk_reports": [{"audio_seconds": 4.0} for _ in chunks]}
    cues = lib.build_cues(book["id"], report)
    assert len(cues) == len(chunks)
    assert cues[0]["start"] == 0.0
    if len(cues) > 1:
        assert cues[1]["start"] == 3.945


def test_dashboard_defaults_are_local_and_focus_friendly(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    dash = lib.dashboard()
    assert dash["voice_ready"] is False
    assert dash["preferences"]["focus_minutes"] == 25
    assert dash["preferences"]["eq_preset"] == "flat"
    assert dash["preferences"]["theme"] == "midnight"
    assert dash["preferences"]["generation_mode"] == "cool"
    assert "storage" in dash


def test_extract_text_rejects_unknown_format(tmp_path: Path):
    source = tmp_path / "book.epub"
    source.write_bytes(b"x")
    try:
        extract_book_text(source)
    except ValueError as exc:
        assert "PDF" in str(exc)
    else:
        raise AssertionError("unsupported format should fail")

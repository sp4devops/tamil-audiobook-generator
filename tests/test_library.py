from pathlib import Path

from tamil_audiobook.library import LocalLibrary, extract_book_text


def test_txt_import_library_state_and_playlist(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("வணக்கம் உலகம். This is a local audiobook test.", encoding="utf-8")
    lib = LocalLibrary(tmp_path / "library")
    book = lib.import_book(source, title="Test Book", author="Test Author", series="Test Series")

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


def test_build_cues_tracks_crossfade(tmp_path: Path):
    source = tmp_path / "book.txt"
    source.write_text("First sentence. Second sentence. Third sentence.", encoding="utf-8")
    lib = LocalLibrary(tmp_path / "library")
    book = lib.import_book(source)

    from tamil_audiobook.engine import chunk_text
    chunks = chunk_text(lib.text(book["id"]))
    report = {
        "crossfade_ms": 55,
        "chunk_reports": [{"audio_seconds": 4.0} for _ in chunks],
    }
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


def test_extract_text_rejects_unknown_format(tmp_path: Path):
    source = tmp_path / "book.epub"
    source.write_bytes(b"x")
    try:
        extract_book_text(source)
    except ValueError as exc:
        assert "PDF" in str(exc)
    else:
        raise AssertionError("unsupported format should fail")

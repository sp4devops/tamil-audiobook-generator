from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "tamil_audiobook" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "tamil_audiobook" / "static" / "app.js").read_text(encoding="utf-8")
PROGRESSIVE = (ROOT / "tamil_audiobook" / "static" / "progressive.js").read_text(encoding="utf-8")
CSS = (ROOT / "tamil_audiobook" / "static" / "enhancements.css").read_text(encoding="utf-8")


def test_generation_progress_and_estimate_controls_exist():
    for token in (
        'id="generationBar"',
        'id="generationPercent"',
        'id="generationEta"',
        'id="generationElapsed"',
        'id="estimatedAudioDuration"',
        'id="estimatedGenerationTime"',
        'id="readerDuration"',
    ):
        assert token in INDEX
    assert "estimated_remaining_seconds" in JS
    assert "completed_chunks" in JS


def test_play_sidebar_and_fullscreen_controls_exist():
    for token in (
        'id="readerPlayButton"',
        'id="toggleNav"',
        'id="toggleSoundPanel"',
        'id="fullscreenButton"',
        'id="playerFullscreen"',
    ):
        assert token in INDEX
    assert "data-play-book" in JS
    assert "requestFullscreen" in JS
    assert "nav-collapsed" in CSS
    assert "sound-collapsed" in CSS
    assert "fullscreen-reading" in CSS


def test_product_voice_contract_requires_original_source():
    lower = INDEX.lower()
    assert "original source voice is required" in lower
    assert "saving a voice here overrides it locally" not in lower
    assert "accepted-c generated mixed voice is the built-in default" not in lower
    assert "original-source-local" in JS
    assert "accepted-c-default" not in JS
    assert "Original source voice saved and normalized locally" in JS


def test_progressive_player_keeps_export_and_cross_chunk_seek():
    assert "Export MP3" in PROGRESSIVE
    assert "seekPartial" in PROGRESSIVE
    assert "activateCue" in PROGRESSIVE
    assert "focus-line-mode" in PROGRESSIVE

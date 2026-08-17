from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "tamil_audiobook" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "tamil_audiobook" / "static" / "app.js").read_text(encoding="utf-8")
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


def test_default_voice_is_described_as_accepted_c():
    assert "accepted-C generated mixed voice is the built-in default" in INDEX
    assert "accepted-c-default" in JS

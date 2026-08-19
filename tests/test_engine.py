from __future__ import annotations

import numpy as np

from tamil_audiobook.engine import (
    DEFAULT_GUIDANCE_SCALE,
    DEFAULT_NUM_STEPS,
    _crossfade_join,
    chunk_text,
    detect_language,
    estimate_audiobook,
    estimate_duration_seconds,
)


def test_accepted_voice_defaults_are_locked():
    assert DEFAULT_NUM_STEPS == 20
    assert DEFAULT_GUIDANCE_SCALE == 2.5


def test_detect_language_modes():
    assert detect_language("இது தமிழ் உரை") == "tamil"
    assert detect_language("This is English text") == "english"
    assert detect_language("இது mixed English உரை") == "None"


def test_chunk_text_preserves_content():
    text = (
        "இது முதல் தமிழ் வாக்கியம். "
        "This is the second English sentence. "
        "இது mixed English sentence ஆகும்."
    )
    chunks = chunk_text(text, target_chars=40, max_chars=80)
    assert chunks
    rebuilt = " ".join(chunk.text for chunk in chunks)
    assert "முதல் தமிழ்" in rebuilt
    assert "second English" in rebuilt
    assert all(0 < len(chunk.text) <= 80 for chunk in chunks)


def test_long_sentence_is_split_under_limit():
    text = " ".join(["word"] * 100)
    chunks = chunk_text(text, target_chars=50, max_chars=80)
    assert len(chunks) > 1
    assert max(len(chunk.text) for chunk in chunks) <= 80


def test_long_sentence_never_moves_before_buffered_earlier_sentence():
    first = "Earlier short sentence."
    long_sentence = " ".join(f"word{i}" for i in range(60)) + "."
    chunks = chunk_text(f"{first} {long_sentence}", target_chars=40, max_chars=80)
    assert chunks[0].text == first
    rebuilt = " ".join(chunk.text for chunk in chunks)
    assert rebuilt.startswith(first + " word0")
    assert rebuilt.index("Earlier") < rebuilt.index("word0") < rebuilt.index("word59")


def test_single_overlong_token_respects_hard_chunk_limit():
    token = "x" * 205
    chunks = chunk_text(token, target_chars=40, max_chars=80)
    assert [len(chunk.text) for chunk in chunks] == [80, 80, 45]
    assert "".join(chunk.text for chunk in chunks) == token


def test_duration_estimate_is_bounded():
    assert 3.0 <= estimate_duration_seconds("short") <= 12.0
    assert estimate_duration_seconds("word " * 200) == 12.0


def test_audiobook_estimate_reports_duration_chunks_and_generation_time():
    estimate = estimate_audiobook("First sentence. Second sentence. Third sentence.")
    assert estimate["chunks"] >= 1
    assert estimate["audio_seconds"] > 0
    assert estimate["generation_seconds"] > estimate["audio_seconds"]
    assert 1.0 < estimate["estimate_rtf"] < 2.0


def test_crossfade_join_reduces_overlap_length():
    rate = 1000
    a = np.ones(1000, dtype=np.float32)
    b = np.ones(1000, dtype=np.float32)
    joined = _crossfade_join([a, b], rate, 100)
    assert len(joined) == 1900
    assert np.isfinite(joined).all()
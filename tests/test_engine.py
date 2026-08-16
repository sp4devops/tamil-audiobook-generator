from __future__ import annotations

import numpy as np

from tamil_audiobook.engine import _crossfade_join, chunk_text, detect_language, estimate_duration_seconds


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


def test_duration_estimate_is_bounded():
    assert 3.0 <= estimate_duration_seconds("short") <= 12.0
    assert estimate_duration_seconds("word " * 200) == 12.0


def test_crossfade_join_reduces_overlap_length():
    rate = 1000
    a = np.ones(1000, dtype=np.float32)
    b = np.ones(1000, dtype=np.float32)
    joined = _crossfade_join([a, b], rate, 100)
    assert len(joined) == 1900
    assert np.isfinite(joined).all()

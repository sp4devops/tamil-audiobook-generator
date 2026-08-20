from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from tamil_audiobook.engine import _checkpoint_key
from tamil_audiobook.pronunciation import apply_pronunciation_overrides, load_overrides
from tamil_audiobook.prosody import PROSODY_VERSION, prosody_for_chunk
from tamil_audiobook.voice import audit_reference_audio, reference_text_warnings


def test_p7_prosody_version_is_bumped():
    assert PROSODY_VERSION >= 4


def test_pure_english_between_tamil_chunks_keeps_indian_english_accent():
    profile = prosody_for_chunk(
        "Did the backup finish?",
        "question",
        previous_text="என்ன நடந்தது?",
        next_text="ஆமாம், backup முடிஞ்சுது.",
    )
    assert profile.name == "indian-english-question"
    assert "South-Indian Tamil bilingual speaker" in profile.instruct
    assert "American or British accent" in profile.instruct


def test_english_only_book_keeps_existing_english_baseline():
    profile = prosody_for_chunk("Did the backup finish?", "question")
    assert profile.name == "question"
    assert "South-Indian Tamil bilingual speaker" not in profile.instruct


def test_context_works_when_tamil_is_only_on_next_chunk():
    profile = prosody_for_chunk(
        "The restore test is still pending.",
        "sentence",
        next_text="ஆனா data safe-ஆ இருக்கு.",
    )
    assert profile.name == "indian-english-continuation"


def test_mixed_script_normalizes_only_known_romanized_tamil_tokens():
    source = "இந்த query romba slow; intha fix panna aaguma nu first check பண்ணலாம்."
    result = apply_pronunciation_overrides(source, load_overrides())
    assert "query" in result.text
    assert "first" in result.text
    assert "check" in result.text
    assert "ரொம்ப" in result.text
    assert "இந்த fix" in result.text
    assert "பண்ண" in result.text
    assert "ஆகுமா" in result.text
    assert "னு" in result.text


def test_ordinary_english_does_not_trigger_tanglish_normalization():
    source = "The data pipeline is ready and the backup is complete."
    result = apply_pronunciation_overrides(source, load_overrides())
    assert result.text == source
    assert result.applied == ()


def test_weak_single_token_does_not_false_positive_in_english():
    source = "Ama is a short name in this English sentence."
    result = apply_pronunciation_overrides(source, load_overrides())
    assert result.text == source


def test_reference_quality_gate_rejects_silence_and_accepts_voiced_audio(tmp_path: Path):
    rate = 24000
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros(rate * 8, dtype=np.float32), rate)
    assert not audit_reference_audio(silent).accepted

    voiced = tmp_path / "voiced.wav"
    t = np.arange(rate * 8, dtype=np.float32) / rate
    audio = (0.12 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    sf.write(voiced, audio, rate)
    report = audit_reference_audio(voiced)
    assert report.accepted
    assert report.active_ratio > 0.5
    assert report.clipping_ratio == 0.0


def test_reference_text_warns_when_bilingual_coverage_is_missing():
    assert "bilingual_reference_coverage_missing" in reference_text_warnings(
        "This is only English reference text"
    )
    assert "bilingual_reference_coverage_missing" not in reference_text_warnings(
        "This is my English voice. இது என் தமிழ் குரல்."
    )


def test_checkpoint_extra_signature_prevents_control_cache_collision(tmp_path: Path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"voice-reference")
    common = dict(
        text="hello",
        reference_audio=ref,
        reference_text="hello",
        num_steps=20,
        guidance_scale=2.5,
        crossfade_ms=55,
        target_chars=140,
        max_chars=220,
        pronunciation_signature="abc",
    )
    assert _checkpoint_key(**common, extra_signature="controls=a") != _checkpoint_key(
        **common,
        extra_signature="controls=b",
    )

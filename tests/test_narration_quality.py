from __future__ import annotations

import numpy as np
import soundfile as sf

from tamil_audiobook.engine import (
    DEFAULT_CROSSFADE_MS,
    _write_stream_part,
    boundary_pause_ms,
)
from tamil_audiobook.library import LocalLibrary
from tamil_audiobook.pronunciation import apply_pronunciation_overrides, load_overrides


def test_boundary_pause_policy_preserves_punctuation_rhythm():
    assert boundary_pause_ms("continuation") == 0
    assert 50 <= boundary_pause_ms("clause") < boundary_pause_ms("sentence")
    assert boundary_pause_ms("question") >= boundary_pause_ms("sentence")
    assert boundary_pause_ms("exclamation") >= boundary_pause_ms("sentence")
    assert boundary_pause_ms("paragraph") > boundary_pause_ms("question")


def test_pronunciation_overrides_only_change_model_facing_tokens():
    source = "டேய் MongoDB API crash ஆயிடுச்சு, seri machi."
    result = apply_pronunciation_overrides(source, load_overrides())
    assert "டேய்" in result.text
    assert "seri machi" in result.text
    assert "Mongo D B" in result.text
    assert "A P I" in result.text
    assert result.applied == ("MongoDB", "API")


def test_user_pronunciation_json_extends_builtin_overrides(tmp_path):
    override = tmp_path / "pronunciation.json"
    override.write_text('{"Sedhupathy": "Sethu pathy", "K8s": "Kubernetes"}', encoding="utf-8")
    mapping = load_overrides(override)
    result = apply_pronunciation_overrides("Sedhupathy uses K8s and MongoDB", mapping)
    assert result.text == "Sethu pathy uses Kubernetes and Mongo D B"
    assert result.applied == ("Sedhupathy", "K8s", "MongoDB")


def test_boundary_writer_inserts_real_silence_but_continuation_crossfades(tmp_path):
    rate = 1000
    fade_samples = int(rate * DEFAULT_CROSSFADE_MS / 1000)
    audio = np.ones(1000, dtype=np.float32)

    punctuated = tmp_path / "punctuated.wav"
    with sf.SoundFile(punctuated, mode="w", samplerate=rate, channels=1, subtype="PCM_16") as writer:
        tail = _write_stream_part(writer, None, audio, fade_samples)
        tail = _write_stream_part(
            writer,
            tail,
            audio,
            fade_samples,
            pause_samples=220,
            edge_fade_samples=15,
        )
        writer.write(tail)
    assert sf.info(punctuated).frames == 2220

    continuation = tmp_path / "continuation.wav"
    with sf.SoundFile(continuation, mode="w", samplerate=rate, channels=1, subtype="PCM_16") as writer:
        tail = _write_stream_part(writer, None, audio, fade_samples)
        tail = _write_stream_part(writer, tail, audio, fade_samples)
        writer.write(tail)
    assert sf.info(continuation).frames == 2000 - fade_samples


def test_read_along_cues_use_engine_absolute_timestamps(tmp_path):
    source = tmp_path / "book.txt"
    source.write_text("First question? Second sentence.", encoding="utf-8")
    library = LocalLibrary(tmp_path / "library")
    book = library.import_book(source)
    report = {
        "crossfade_ms": 55,
        "chunk_reports": [
            {"audio_seconds": 1.0, "audio_start": 0.0, "audio_end": 1.0},
            {"audio_seconds": 1.0, "audio_start": 1.26, "audio_end": 2.26},
        ],
    }
    cues = library.build_cues(book["id"], report)
    assert len(cues) == 2
    assert cues[0]["start"] == 0.0
    assert cues[0]["end"] == 1.0
    assert cues[1]["start"] == 1.26
    assert cues[1]["end"] == 2.26
    assert cues[0]["text"] == "First question?"
    assert cues[1]["text"] == "Second sentence."

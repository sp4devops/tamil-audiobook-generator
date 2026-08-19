from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tamil_audiobook.library import LocalLibrary
from tamil_audiobook.voice import (
    DEFAULT_VOICE_PROVENANCE,
    GENERATED_FALLBACK_LABEL,
    ORIGINAL_SOURCE_LABEL,
    _decode_default_opus,
    _valid_reference_audio,
    default_voice_available,
    materialize_default_voice,
    original_voice_available,
    resolve_voice,
)


def test_packaged_generated_fallback_integrity_and_audio(tmp_path: Path):
    assert default_voice_available()
    raw = _decode_default_opus()
    assert len(raw) > 8000
    assert raw.startswith(b"OggS")
    assert "8.52-second bilingual excerpt" in DEFAULT_VOICE_PROVENANCE
    assert "extracted from the Final 11-minute accepted-C audiobook MP3" in DEFAULT_VOICE_PROVENANCE

    wav, transcript = materialize_default_voice(tmp_path / "cache")
    info = sf.info(wav)
    assert info.samplerate == 24000
    assert info.channels == 1
    assert 8.0 * info.samplerate < info.frames < 9.0 * info.samplerate
    assert "transition should remain natural" in transcript
    assert "தொடர்ந்து" in transcript


def test_source_voice_requires_24khz_mono_audio(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    audio, transcript = lib.voice_reference_paths()
    transcript.write_text("exact source transcript", encoding="utf-8")

    sf.write(audio, np.zeros(48000, dtype=np.float32), 48000)
    assert not _valid_reference_audio(audio)
    assert not original_voice_available(lib)

    sf.write(audio, np.zeros((48000, 2), dtype=np.float32), 24000)
    assert not _valid_reference_audio(audio)
    assert not original_voice_available(lib)

    sf.write(audio, np.zeros(48000, dtype=np.float32), 24000)
    assert _valid_reference_audio(audio)
    assert original_voice_available(lib)


def test_source_voice_rejects_pathological_duration(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    audio, transcript = lib.voice_reference_paths()
    transcript.write_text("exact source transcript", encoding="utf-8")

    sf.write(audio, np.zeros(12000, dtype=np.float32), 24000)
    assert not original_voice_available(lib)


def test_resolve_voice_requires_original_and_never_silently_falls_back(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")

    with pytest.raises(FileNotFoundError, match="Original source voice"):
        resolve_voice(lib)

    fallback_audio, fallback_text, fallback_source = resolve_voice(lib, allow_generated_fallback=True)
    assert fallback_source == GENERATED_FALLBACK_LABEL
    assert fallback_audio.is_file()
    assert fallback_text.strip()

    # A locally stored source recording always wins over the generated fallback.
    lib.save_voice_reference(fallback_audio, "original source reference words")
    audio, transcript, source = resolve_voice(lib)
    assert source == ORIGINAL_SOURCE_LABEL
    assert audio.is_file()
    assert transcript == "original source reference words"

    audio2, transcript2, source2 = resolve_voice(lib, allow_generated_fallback=True)
    assert source2 == ORIGINAL_SOURCE_LABEL
    assert audio2 == audio
    assert transcript2 == transcript

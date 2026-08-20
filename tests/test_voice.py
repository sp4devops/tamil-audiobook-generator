from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tamil_audiobook.library import LocalLibrary
from tamil_audiobook.voice import (
    ORIGINAL_SOURCE_LABEL,
    _valid_reference_audio,
    audit_reference_audio,
    default_voice_available,
    materialize_default_voice,
    normalize_reference_audio,
    original_voice_available,
    resolve_voice,
)


def _tone(seconds: float, rate: int = 24000, channels: int = 1) -> np.ndarray:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    mono = (0.12 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    return np.column_stack([mono] * channels) if channels > 1 else mono


def test_no_generated_or_private_voice_is_packaged(tmp_path: Path):
    assert not default_voice_available()
    with pytest.raises(FileNotFoundError, match="No generated fallback voice is packaged"):
        materialize_default_voice(tmp_path / "cache")
    source_tree = Path(__file__).parents[1] / "tamil_audiobook" / "default_voice"
    assert not list(source_tree.glob("*.opus"))
    assert not list(source_tree.glob("*.b64*"))


def test_source_voice_requires_24khz_mono_audio_and_real_signal(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    audio, transcript = lib.voice_reference_paths()
    transcript.write_text("exact source transcript", encoding="utf-8")

    sf.write(audio, _tone(2, 48000), 48000)
    assert not _valid_reference_audio(audio)
    assert not original_voice_available(lib)

    sf.write(audio, _tone(2, 24000, 2), 24000)
    assert not _valid_reference_audio(audio)
    assert not original_voice_available(lib)

    sf.write(audio, np.zeros(48000, dtype=np.float32), 24000)
    assert _valid_reference_audio(audio)
    assert not audit_reference_audio(audio).accepted
    assert not original_voice_available(lib)

    sf.write(audio, _tone(2), 24000)
    assert audit_reference_audio(audio).accepted
    assert original_voice_available(lib)


def test_source_voice_rejects_pathological_duration(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    audio, transcript = lib.voice_reference_paths()
    transcript.write_text("exact source transcript", encoding="utf-8")
    sf.write(audio, _tone(0.5), 24000)
    assert not original_voice_available(lib)


def test_normalization_accepts_non_wav_and_canonicalizes_rate_and_channels(tmp_path: Path):
    source = tmp_path / "source.flac"
    target = tmp_path / "normalized.wav"
    sf.write(source, _tone(2, 48000, 2), 48000, format="FLAC")
    report = normalize_reference_audio(source, target)
    info = sf.info(target)
    assert report.accepted
    assert info.samplerate == 24000
    assert info.channels == 1
    assert original_voice_available(_library_with_reference(tmp_path / "normalized-library", target))


def test_invalid_wav_is_rejected_before_configuration(tmp_path: Path):
    source = tmp_path / "invalid.wav"
    source.write_bytes(b"RIFF this is not a valid wave")
    with pytest.raises(ValueError, match="could not be decoded"):
        normalize_reference_audio(source, tmp_path / "normalized.wav")


def _library_with_reference(root: Path, audio: Path) -> LocalLibrary:
    lib = LocalLibrary(root)
    lib.save_voice_reference(audio, "this is the exact source transcript for local validation")
    return lib


def test_resolve_voice_requires_valid_original_and_never_silently_falls_back(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    with pytest.raises(FileNotFoundError, match="Original source voice"):
        resolve_voice(lib)
    with pytest.raises(FileNotFoundError, match="Original source voice"):
        resolve_voice(lib, allow_generated_fallback=True)

    candidate = tmp_path / "candidate.wav"
    sf.write(candidate, _tone(2), 24000)
    lib.save_voice_reference(candidate, "original source reference words for the configured voice")
    audio, transcript, source = resolve_voice(lib)
    assert source == ORIGINAL_SOURCE_LABEL
    assert audio.is_file()
    assert transcript == "original source reference words for the configured voice"

from pathlib import Path

import soundfile as sf

from tamil_audiobook.library import LocalLibrary
from tamil_audiobook.voice import (
    DEFAULT_VOICE_OPUS_SHA256,
    DEFAULT_VOICE_PROVENANCE,
    _decode_default_opus,
    default_voice_available,
    materialize_default_voice,
    resolve_voice,
)


def test_packaged_default_voice_checksum_and_audio(tmp_path: Path):
    assert default_voice_available()
    import hashlib

    raw = _decode_default_opus()
    assert hashlib.sha256(raw).hexdigest() == DEFAULT_VOICE_OPUS_SHA256
    assert "8.52-second bilingual excerpt" in DEFAULT_VOICE_PROVENANCE
    assert "accepted C" in DEFAULT_VOICE_PROVENANCE

    wav, transcript = materialize_default_voice(tmp_path / "cache")
    info = sf.info(wav)
    assert info.samplerate == 24000
    assert info.channels == 1
    assert 8.0 * info.samplerate < info.frames < 9.0 * info.samplerate
    assert "transition should remain natural" in transcript
    assert "தொடர்ந்து" in transcript


def test_resolve_voice_uses_default_then_custom_override(tmp_path: Path):
    lib = LocalLibrary(tmp_path / "library")
    audio, transcript, source = resolve_voice(lib)
    assert source == "accepted-c-default"
    assert audio.is_file()
    assert transcript.strip()

    custom = tmp_path / "custom.wav"
    custom.write_bytes(audio.read_bytes())
    lib.save_voice_reference(custom, "custom reference words")
    audio2, transcript2, source2 = resolve_voice(lib)
    assert source2 == "custom"
    assert transcript2 == "custom reference words"

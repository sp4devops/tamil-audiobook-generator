from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_VOICE_ROOT = PACKAGE_ROOT / "default_voice"
DEFAULT_VOICE_GLOB = "accepted_c_default.flac.b64.part*"
DEFAULT_VOICE_FLAC_SHA256 = "2db888fae059ef6769df8425217a906f1df7099b941e1050eeab32a115faa719"
# Transcript for the safe generated Stage-1 mixed listening reference.
DEFAULT_VOICE_TEXT = "வணக்கம், this is my voice. இன்று Kubernetes சரியாக வேலை செய்கிறது."


def _parts() -> list[Path]:
    return sorted(DEFAULT_VOICE_ROOT.glob(DEFAULT_VOICE_GLOB))


def default_voice_available() -> bool:
    parts = _parts()
    return len(parts) == 3 and all(part.is_file() and part.stat().st_size > 1000 for part in parts)


def _decode_default_flac() -> bytes:
    if not default_voice_available():
        raise FileNotFoundError("packaged accepted-C default voice is missing")
    encoded = "".join(part.read_text(encoding="utf-8").strip() for part in _parts())
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != DEFAULT_VOICE_FLAC_SHA256:
        raise RuntimeError("packaged default voice checksum mismatch")
    return raw


def materialize_default_voice(cache_root: Path) -> tuple[Path, str]:
    cache_root.mkdir(parents=True, exist_ok=True)
    flac_path = cache_root / "accepted_c_default.flac"
    wav_path = cache_root / "accepted_c_default.wav"
    raw = _decode_default_flac()
    if not flac_path.is_file() or hashlib.sha256(flac_path.read_bytes()).hexdigest() != DEFAULT_VOICE_FLAC_SHA256:
        flac_path.write_bytes(raw)
        wav_path.unlink(missing_ok=True)
    if not wav_path.is_file() or wav_path.stat().st_size < 1000:
        # The packaged FLAC is a lossless representation of the exact accepted 24 kHz mono PCM reference.
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(flac_path), str(wav_path)],
            check=True,
        )
    return wav_path, DEFAULT_VOICE_TEXT


def resolve_voice(library) -> tuple[Path, str, str]:
    custom_audio, custom_text = library.voice_reference_paths()
    if custom_audio.is_file() and custom_text.is_file():
        transcript = custom_text.read_text(encoding="utf-8").strip()
        if transcript:
            return custom_audio, transcript, "custom"
    audio, transcript = materialize_default_voice(library.cache_root)
    return audio, transcript, "accepted-c-default"

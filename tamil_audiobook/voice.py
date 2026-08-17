from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_VOICE_PAYLOAD = PACKAGE_ROOT / "default_voice" / "accepted_c_default.opus.b64"
DEFAULT_VOICE_OPUS_SHA256 = "b21cb960523e7522822d613ce17544c6b9b36c0a4fdf5d39f50918a4b79efb71"
# This is the transcript of the safe generated Stage-1 mixed listening sample.
DEFAULT_VOICE_TEXT = "வணக்கம், this is my voice. இன்று Kubernetes சரியாக வேலை செய்கிறது."


def default_voice_available() -> bool:
    return DEFAULT_VOICE_PAYLOAD.is_file() and DEFAULT_VOICE_PAYLOAD.stat().st_size > 1000


def materialize_default_voice(cache_root: Path) -> tuple[Path, str]:
    if not default_voice_available():
        raise FileNotFoundError("packaged accepted-C default voice is missing")
    cache_root.mkdir(parents=True, exist_ok=True)
    opus_path = cache_root / "accepted_c_default.opus"
    wav_path = cache_root / "accepted_c_default.wav"
    raw = base64.b64decode(DEFAULT_VOICE_PAYLOAD.read_text(encoding="utf-8"))
    digest = hashlib.sha256(raw).hexdigest()
    if digest != DEFAULT_VOICE_OPUS_SHA256:
        raise RuntimeError("packaged default voice checksum mismatch")
    if not opus_path.is_file() or hashlib.sha256(opus_path.read_bytes()).hexdigest() != digest:
        opus_path.write_bytes(raw)
    if not wav_path.is_file() or wav_path.stat().st_size < 1000:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(opus_path), "-ac", "1", "-ar", "24000", str(wav_path),
            ],
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

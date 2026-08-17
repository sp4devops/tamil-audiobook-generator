from __future__ import annotations

import base64
import hashlib
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_VOICE_ROOT = PACKAGE_ROOT / "default_voice"
DEFAULT_VOICE_GLOB = "final_11min_accepted_c.opus.b64.part*"
DEFAULT_VOICE_OPUS_SHA256 = "51afd8c66adfac4906f36080e327331bfc2b16638a95f605452f1f1c2b162802"
DEFAULT_VOICE_PROVENANCE = "Final 11-minute accepted-C audiobook MP3"
# Exact text spoken in the selected 8.52-second bilingual segment of the final accepted audiobook.
DEFAULT_VOICE_TEXT = "The transition should remain natural and consistent. கதை தொடர்ந்து செல்லும் போது ஒவ்வொரு வாக்கியத்திலும் உச்சரிப்பு தெளிவாக இருக்க வேண்டும்."


def _parts() -> list[Path]:
    return sorted(DEFAULT_VOICE_ROOT.glob(DEFAULT_VOICE_GLOB))


def default_voice_available() -> bool:
    parts = _parts()
    return len(parts) == 4 and all(part.is_file() and part.stat().st_size > 1000 for part in parts)


def _decode_default_opus() -> bytes:
    if not default_voice_available():
        raise FileNotFoundError("packaged final accepted-C default voice is missing")
    encoded = "".join(part.read_text(encoding="utf-8").strip() for part in _parts())
    raw = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(raw).hexdigest() != DEFAULT_VOICE_OPUS_SHA256:
        raise RuntimeError("packaged final accepted-C voice checksum mismatch")
    return raw


def materialize_default_voice(cache_root: Path) -> tuple[Path, str]:
    cache_root.mkdir(parents=True, exist_ok=True)
    opus_path = cache_root / "final_11min_accepted_c.opus"
    wav_path = cache_root / "final_11min_accepted_c.wav"
    raw = _decode_default_opus()
    if not opus_path.is_file() or hashlib.sha256(opus_path.read_bytes()).hexdigest() != DEFAULT_VOICE_OPUS_SHA256:
        opus_path.write_bytes(raw)
        wav_path.unlink(missing_ok=True)
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

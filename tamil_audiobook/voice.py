from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_VOICE_ROOT = PACKAGE_ROOT / "default_voice"
DEFAULT_VOICE_OPUS = DEFAULT_VOICE_ROOT / "final_11min_accepted_c.opus"
DEFAULT_VOICE_SHA256 = "51afd8c66adfac4906f36080e327331bfc2b16638a95f605452f1f1c2b162802"
DEFAULT_VOICE_PROVENANCE = "8.52-second bilingual excerpt extracted from the Final 11-minute accepted-C audiobook MP3"
# Exact transcript matching the selected bilingual excerpt from the accepted audiobook.
DEFAULT_VOICE_TEXT = "The transition should remain natural and consistent. கதை தொடர்ந்து செல்லும் போது ஒவ்வொரு வாக்கியத்திலும் உச்சரிப்பு தெளிவாக இருக்க வேண்டும்."


def default_voice_available() -> bool:
    if not DEFAULT_VOICE_OPUS.is_file() or DEFAULT_VOICE_OPUS.stat().st_size < 8000:
        return False
    return hashlib.sha256(DEFAULT_VOICE_OPUS.read_bytes()).hexdigest() == DEFAULT_VOICE_SHA256


def _decode_default_opus() -> bytes:
    if not default_voice_available():
        raise FileNotFoundError("verified final accepted-C default voice asset is missing or corrupted")
    raw = DEFAULT_VOICE_OPUS.read_bytes()
    if not raw.startswith(b"OggS"):
        raise RuntimeError("packaged accepted-C default voice is not a valid Ogg/Opus payload")
    return raw


def materialize_default_voice(cache_root: Path) -> tuple[Path, str]:
    cache_root.mkdir(parents=True, exist_ok=True)
    opus_path = cache_root / "accepted_c_default.opus"
    wav_path = cache_root / "accepted_c_default.wav"
    raw = _decode_default_opus()
    cached_digest = hashlib.sha256(opus_path.read_bytes()).hexdigest() if opus_path.is_file() else None
    if cached_digest != DEFAULT_VOICE_SHA256:
        shutil.copy2(DEFAULT_VOICE_OPUS, opus_path)
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

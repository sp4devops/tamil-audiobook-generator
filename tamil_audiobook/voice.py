from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_VOICE_ROOT = PACKAGE_ROOT / "default_voice"
# This generated reference is retained only as an explicit emergency/test fallback.
GENERATED_FALLBACK_OPUS = DEFAULT_VOICE_ROOT / "final_11min_accepted_c.opus"
GENERATED_FALLBACK_SHA256 = "51afd8c66adfac4906f36080e327331bfc2b16638a95f605452f1f1c2b162802"
GENERATED_FALLBACK_PROVENANCE = "8.52-second bilingual excerpt extracted from the Final 11-minute accepted-C audiobook MP3"
GENERATED_FALLBACK_TEXT = "The transition should remain natural and consistent. கதை தொடர்ந்து செல்லும் போது ஒவ்வொரு வாக்கியத்திலும் உச்சரிப்பு தெளிவாக இருக்க வேண்டும்."

ORIGINAL_SOURCE_LABEL = "original-source-local"
GENERATED_FALLBACK_LABEL = "accepted-c-generated-fallback"
ORIGINAL_REQUIRED_LABEL = "original-source-required"

# Backward-compatible constant names for tooling/tests that inspect the packaged fallback.
DEFAULT_VOICE_OPUS = GENERATED_FALLBACK_OPUS
DEFAULT_VOICE_SHA256 = GENERATED_FALLBACK_SHA256
DEFAULT_VOICE_PROVENANCE = GENERATED_FALLBACK_PROVENANCE
DEFAULT_VOICE_TEXT = GENERATED_FALLBACK_TEXT


def original_voice_available(library) -> bool:
    audio, text = library.voice_reference_paths()
    if not audio.is_file() or not text.is_file():
        return False
    try:
        return audio.stat().st_size > 1000 and bool(text.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def default_voice_available() -> bool:
    """Return whether the packaged generated fallback is intact.

    Kept for backward compatibility. This is no longer the product's canonical
    default voice and is never selected silently by resolve_voice().
    """
    if not GENERATED_FALLBACK_OPUS.is_file() or GENERATED_FALLBACK_OPUS.stat().st_size < 8000:
        return False
    return hashlib.sha256(GENERATED_FALLBACK_OPUS.read_bytes()).hexdigest() == GENERATED_FALLBACK_SHA256


def _decode_default_opus() -> bytes:
    if not default_voice_available():
        raise FileNotFoundError("verified generated fallback voice asset is missing or corrupted")
    raw = GENERATED_FALLBACK_OPUS.read_bytes()
    if not raw.startswith(b"OggS"):
        raise RuntimeError("packaged generated fallback is not a valid Ogg/Opus payload")
    return raw


def materialize_default_voice(cache_root: Path) -> tuple[Path, str]:
    """Materialize the generated accepted-C fallback for tests/emergency use only."""
    cache_root.mkdir(parents=True, exist_ok=True)
    opus_path = cache_root / "accepted_c_generated_fallback.opus"
    wav_path = cache_root / "accepted_c_generated_fallback.wav"
    raw = _decode_default_opus()
    cached_digest = hashlib.sha256(opus_path.read_bytes()).hexdigest() if opus_path.is_file() else None
    if cached_digest != GENERATED_FALLBACK_SHA256:
        shutil.copy2(GENERATED_FALLBACK_OPUS, opus_path)
        wav_path.unlink(missing_ok=True)
    if not wav_path.is_file() or wav_path.stat().st_size < 1000:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(opus_path), "-ac", "1", "-ar", "24000", str(wav_path),
            ],
            check=True,
        )
    return wav_path, GENERATED_FALLBACK_TEXT


def resolve_voice(library, *, allow_generated_fallback: bool = False) -> tuple[Path, str, str]:
    """Resolve the voice used for synthesis.

    Product default is the user's original source recording stored locally.
    The generated accepted-C reference is available only when a caller opts in
    explicitly; it is never used silently by the web app or normal CLI flow.
    """
    audio, text = library.voice_reference_paths()
    if original_voice_available(library):
        transcript = text.read_text(encoding="utf-8").strip()
        return audio, transcript, ORIGINAL_SOURCE_LABEL

    if allow_generated_fallback:
        fallback_audio, fallback_text = materialize_default_voice(library.cache_root)
        return fallback_audio, fallback_text, GENERATED_FALLBACK_LABEL

    raise FileNotFoundError(
        "Original source voice is not configured locally. Add the original recording and its exact transcript in Settings before generating."
    )

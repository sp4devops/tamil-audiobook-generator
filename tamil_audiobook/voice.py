from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_VOICE_ROOT = PACKAGE_ROOT / "default_voice"
GENERATED_FALLBACK_OPUS = DEFAULT_VOICE_ROOT / "final_11min_accepted_c.opus"
GENERATED_FALLBACK_SHA256 = "51afd8c66adfac4906f36080e327331bfc2b16638a95f605452f1f1c2b162802"
GENERATED_FALLBACK_PROVENANCE = "8.52-second bilingual excerpt extracted from the Final 11-minute accepted-C audiobook MP3"
GENERATED_FALLBACK_TEXT = "The transition should remain natural and consistent. கதை தொடர்ந்து செல்லும் போது ஒவ்வொரு வாக்கியத்திலும் உச்சரிப்பு தெளிவாக இருக்க வேண்டும்."

ORIGINAL_SOURCE_LABEL = "original-source-local"
GENERATED_FALLBACK_LABEL = "accepted-c-generated-fallback"
ORIGINAL_REQUIRED_LABEL = "original-source-required"
REFERENCE_SAMPLE_RATE = 24000
REFERENCE_CHANNELS = 1
MIN_REFERENCE_SECONDS = 1.0
MAX_REFERENCE_SECONDS = 120.0
PREFERRED_REFERENCE_SECONDS = (6.0, 30.0)

DEFAULT_VOICE_OPUS = GENERATED_FALLBACK_OPUS
DEFAULT_VOICE_SHA256 = GENERATED_FALLBACK_SHA256
DEFAULT_VOICE_PROVENANCE = GENERATED_FALLBACK_PROVENANCE
DEFAULT_VOICE_TEXT = GENERATED_FALLBACK_TEXT


@dataclass(frozen=True)
class ReferenceQualityReport:
    accepted: bool
    duration_seconds: float
    peak: float
    rms_db: float | None
    active_ratio: float
    clipping_ratio: float
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "duration_seconds": round(self.duration_seconds, 3),
            "peak": round(self.peak, 5),
            "rms_db": round(self.rms_db, 2) if self.rms_db is not None else None,
            "active_ratio": round(self.active_ratio, 4),
            "clipping_ratio": round(self.clipping_ratio, 6),
            "warnings": list(self.warnings),
        }


def _valid_reference_audio(path: Path) -> bool:
    """Validate the normalized source reference container and duration."""
    try:
        if not path.is_file() or path.stat().st_size < 1000:
            return False
        info = sf.info(path)
        if info.samplerate != REFERENCE_SAMPLE_RATE or info.channels != REFERENCE_CHANNELS:
            return False
        if info.frames <= 0:
            return False
        duration = info.frames / float(info.samplerate)
        return MIN_REFERENCE_SECONDS <= duration <= MAX_REFERENCE_SECONDS
    except (OSError, RuntimeError, ValueError):
        return False


def audit_reference_audio(path: Path) -> ReferenceQualityReport:
    """Run a lightweight local quality gate for clone-reference audio.

    This intentionally avoids ASR/cloud dependencies. It catches references that
    are structurally valid but useless for cloning: silence, almost-no-speech,
    severe clipping, and extreme level/duration. Soft issues remain warnings so a
    user can still choose an unusual but valid recording.
    """
    if not _valid_reference_audio(path):
        return ReferenceQualityReport(
            False,
            0.0,
            0.0,
            None,
            0.0,
            0.0,
            ("invalid_format_or_duration",),
        )
    try:
        audio, rate = sf.read(path, dtype="float32", always_2d=False)
    except (OSError, RuntimeError, ValueError):
        return ReferenceQualityReport(False, 0.0, 0.0, None, 0.0, 0.0, ("unreadable_audio",))

    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    duration = len(samples) / float(rate)
    absolute = np.abs(samples)
    peak = float(np.max(absolute)) if len(samples) else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) if len(samples) else 0.0
    rms_db = float(20.0 * np.log10(rms)) if rms > 1e-8 else None
    active_threshold = max(0.004, peak * 0.025)
    active_ratio = float(np.mean(absolute >= active_threshold)) if len(samples) else 0.0
    clipping_ratio = float(np.mean(absolute >= 0.995)) if len(samples) else 0.0

    warnings: list[str] = []
    hard_fail = False
    if peak < 0.01 or rms < 0.002:
        warnings.append("reference_is_silent_or_too_quiet")
        hard_fail = True
    if active_ratio < 0.12:
        warnings.append("too_little_voiced_audio")
        hard_fail = True
    if clipping_ratio > 0.01:
        warnings.append("severe_clipping")
        hard_fail = True
    elif clipping_ratio > 0.001:
        warnings.append("some_clipping_detected")
    if duration < PREFERRED_REFERENCE_SECONDS[0]:
        warnings.append("reference_shorter_than_preferred_6s")
    elif duration > PREFERRED_REFERENCE_SECONDS[1]:
        warnings.append("reference_longer_than_preferred_30s")
    if rms_db is not None and rms_db < -32.0:
        warnings.append("reference_level_is_low")
    if rms_db is not None and rms_db > -5.0:
        warnings.append("reference_level_is_hot")

    return ReferenceQualityReport(
        accepted=not hard_fail,
        duration_seconds=duration,
        peak=peak,
        rms_db=rms_db,
        active_ratio=active_ratio,
        clipping_ratio=clipping_ratio,
        warnings=tuple(warnings),
    )


def reference_text_warnings(transcript: str) -> tuple[str, ...]:
    text = str(transcript or "").strip()
    warnings: list[str] = []
    if len(text.split()) < 4:
        warnings.append("reference_transcript_is_very_short")
    has_tamil = any("\u0B80" <= ch <= "\u0BFF" for ch in text)
    has_latin = any(ch.isascii() and ch.isalpha() for ch in text)
    if not (has_tamil and has_latin):
        warnings.append("bilingual_reference_coverage_missing")
    return tuple(warnings)


def original_voice_available(library) -> bool:
    audio, text = library.voice_reference_paths()
    if not _valid_reference_audio(audio) or not text.is_file():
        return False
    try:
        transcript = text.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(transcript) and audit_reference_audio(audio).accepted


def default_voice_available() -> bool:
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
    cache_root.mkdir(parents=True, exist_ok=True)
    opus_path = cache_root / "accepted_c_generated_fallback.opus"
    wav_path = cache_root / "accepted_c_generated_fallback.wav"
    raw = _decode_default_opus()
    cached_digest = hashlib.sha256(opus_path.read_bytes()).hexdigest() if opus_path.is_file() else None
    if cached_digest != GENERATED_FALLBACK_SHA256:
        shutil.copy2(GENERATED_FALLBACK_OPUS, opus_path)
        wav_path.unlink(missing_ok=True)
    if not _valid_reference_audio(wav_path):
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(opus_path), "-ac", "1", "-ar", str(REFERENCE_SAMPLE_RATE), str(wav_path),
            ],
            check=True,
        )
    if not _valid_reference_audio(wav_path):
        raise RuntimeError("generated fallback could not be materialized as valid 24 kHz mono audio")
    return wav_path, GENERATED_FALLBACK_TEXT


def resolve_voice(library, *, allow_generated_fallback: bool = False) -> tuple[Path, str, str]:
    audio, text = library.voice_reference_paths()
    if original_voice_available(library):
        transcript = text.read_text(encoding="utf-8").strip()
        return audio, transcript, ORIGINAL_SOURCE_LABEL

    if allow_generated_fallback:
        fallback_audio, fallback_text = materialize_default_voice(library.cache_root)
        return fallback_audio, fallback_text, GENERATED_FALLBACK_LABEL

    raise FileNotFoundError(
        "Original source voice is not configured locally or did not pass the local quality gate. "
        "Add a clean 24 kHz mono source recording with its exact transcript in Settings before generating."
    )

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

ORIGINAL_SOURCE_LABEL = "original-source-local"
ORIGINAL_REQUIRED_LABEL = "original-source-required"
REFERENCE_SAMPLE_RATE = 24000
REFERENCE_CHANNELS = 1
MIN_REFERENCE_SECONDS = 1.0
MAX_REFERENCE_SECONDS = 120.0
PREFERRED_REFERENCE_SECONDS = (6.0, 30.0)
SUPPORTED_REFERENCE_SUFFIXES = {".wav", ".mp3", ".m4a", ".opus", ".flac"}


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


def valid_reference_audio(path: Path) -> bool:
    """Validate the canonical normalized reference container and duration."""
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


# Backward-compatible private alias for older callers/tests.
_valid_reference_audio = valid_reference_audio


def audit_reference_audio(path: Path) -> ReferenceQualityReport:
    """Run the local structural and signal-quality gate for clone references."""
    if not valid_reference_audio(path):
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


def normalize_reference_audio(source: Path, destination: Path) -> ReferenceQualityReport:
    """Normalize a common local audio format to the one canonical clone format.

    The destination is replaced atomically only after ffmpeg output passes both
    structural and signal-quality validation. A bad source can therefore never
    become the configured reference merely because it has a .wav extension.
    """
    source = Path(source)
    destination = Path(destination)
    if source.suffix.lower() not in SUPPORTED_REFERENCE_SUFFIXES:
        raise ValueError("Unsupported reference audio format")
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("Reference audio is missing or empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.stem + ".", suffix=".wav", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-ac",
                str(REFERENCE_CHANNELS),
                "-ar",
                str(REFERENCE_SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                str(temp),
            ],
            check=True,
        )
        report = audit_reference_audio(temp)
        if not report.accepted:
            details = ", ".join(report.warnings) or "reference failed validation"
            raise ValueError(f"Reference audio rejected: {details}")
        os.replace(temp, destination)
        destination.chmod(0o600)
        return report
    except subprocess.CalledProcessError as exc:
        raise ValueError("Reference audio could not be decoded and normalized locally") from exc
    finally:
        temp.unlink(missing_ok=True)


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
    if not valid_reference_audio(audio) or not text.is_file():
        return False
    try:
        transcript = text.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(transcript) and audit_reference_audio(audio).accepted


def default_voice_available() -> bool:
    """No identifying/generated fallback voice is distributed in source."""
    return False


def materialize_default_voice(cache_root: Path) -> tuple[Path, str]:
    del cache_root
    raise FileNotFoundError(
        "No generated fallback voice is packaged for privacy. Configure or securely provision a local source voice."
    )


def resolve_voice(library, *, allow_generated_fallback: bool = False) -> tuple[Path, str, str]:
    del allow_generated_fallback
    audio, text = library.voice_reference_paths()
    if original_voice_available(library):
        transcript = text.read_text(encoding="utf-8").strip()
        return audio, transcript, ORIGINAL_SOURCE_LABEL
    raise FileNotFoundError(
        "Original source voice is not configured locally or did not pass the local quality gate. "
        "Add a clean source recording with its exact transcript in Settings before generating."
    )

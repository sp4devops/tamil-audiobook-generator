from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CONTINUITY_VERSION = "p4-v1"
MAX_GAIN_DB = 1.25
PEAK_LIMIT = 0.98
SILENCE_RMS = 1e-4
REFERENCE_WINDOW = 5


@dataclass(frozen=True)
class ContinuityResult:
    audio: np.ndarray
    level_db: float | None
    reference_db: float | None
    requested_gain_db: float
    applied_gain_db: float
    peak_before: float
    peak_after: float


def active_rms_db(audio: np.ndarray) -> float | None:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not len(samples):
        return None
    absolute = np.abs(samples)
    # Ignore near-digital-silence samples so pauses and edge fades do not
    # distort the narration-level estimate.
    active = samples[absolute >= 1e-4]
    if not len(active):
        return None
    rms = float(np.sqrt(np.mean(np.square(active, dtype=np.float64))))
    if not np.isfinite(rms) or rms < SILENCE_RMS:
        return None
    return float(20.0 * np.log10(rms))


def rolling_reference_db(levels: list[float], window: int = REFERENCE_WINDOW) -> float | None:
    usable = [float(value) for value in levels[-max(1, int(window)) :] if np.isfinite(value)]
    if not usable:
        return None
    return float(np.median(np.asarray(usable, dtype=np.float64)))


def match_chunk_level(audio: np.ndarray, reference_db: float | None) -> ContinuityResult:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1).copy()
    level_db = active_rms_db(samples)
    peak_before = float(np.max(np.abs(samples))) if len(samples) else 0.0

    if level_db is None or reference_db is None or peak_before <= 0.0:
        return ContinuityResult(
            audio=samples,
            level_db=level_db,
            reference_db=reference_db,
            requested_gain_db=0.0,
            applied_gain_db=0.0,
            peak_before=peak_before,
            peak_after=peak_before,
        )

    requested = float(np.clip(reference_db - level_db, -MAX_GAIN_DB, MAX_GAIN_DB))
    peak_safe_db = float(20.0 * np.log10(PEAK_LIMIT / peak_before)) if peak_before > 0 else MAX_GAIN_DB
    applied = min(requested, peak_safe_db) if requested > 0.0 else requested
    gain = float(10.0 ** (applied / 20.0))
    samples *= gain
    samples = np.clip(samples, -PEAK_LIMIT, PEAK_LIMIT).astype(np.float32, copy=False)
    peak_after = float(np.max(np.abs(samples))) if len(samples) else 0.0

    return ContinuityResult(
        audio=samples,
        level_db=level_db,
        reference_db=reference_db,
        requested_gain_db=requested,
        applied_gain_db=applied,
        peak_before=peak_before,
        peak_after=peak_after,
    )

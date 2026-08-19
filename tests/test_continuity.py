import numpy as np

from tamil_audiobook.continuity import (
    MAX_GAIN_DB,
    PEAK_LIMIT,
    active_rms_db,
    match_chunk_level,
    rolling_reference_db,
)


def test_silence_is_left_untouched():
    audio = np.zeros(4000, dtype=np.float32)
    result = match_chunk_level(audio, -20.0)
    assert result.level_db is None
    assert result.applied_gain_db == 0.0
    assert np.array_equal(result.audio, audio)


def test_gain_matching_is_bounded():
    audio = np.full(4000, 0.03, dtype=np.float32)
    result = match_chunk_level(audio, -10.0)
    assert 0.0 < result.applied_gain_db <= MAX_GAIN_DB
    assert result.peak_after <= PEAK_LIMIT


def test_attenuation_is_bounded():
    audio = np.full(4000, 0.5, dtype=np.float32)
    result = match_chunk_level(audio, -30.0)
    assert -MAX_GAIN_DB <= result.applied_gain_db < 0.0
    assert result.peak_after < result.peak_before


def test_peak_protection_can_reduce_positive_gain():
    audio = np.full(4000, 0.97, dtype=np.float32)
    result = match_chunk_level(audio, 0.0)
    assert result.peak_after <= PEAK_LIMIT + 1e-6
    assert result.applied_gain_db <= MAX_GAIN_DB


def test_rolling_reference_uses_recent_median():
    assert rolling_reference_db([]) is None
    assert rolling_reference_db([-20.0, -19.0, -30.0]) == -20.0
    levels = [-50.0, -21.0, -20.0, -19.0, -18.0, -17.0]
    assert rolling_reference_db(levels) == -19.0


def test_adjustment_moves_level_toward_reference_without_flattening():
    audio = np.full(8000, 0.05, dtype=np.float32)
    before = active_rms_db(audio)
    assert before is not None
    reference = before + 3.0
    result = match_chunk_level(audio, reference)
    after = active_rms_db(result.audio)
    assert after is not None
    assert before < after < reference
    assert abs(result.applied_gain_db - MAX_GAIN_DB) < 1e-6

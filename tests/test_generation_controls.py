from __future__ import annotations

import pytest

from tamil_audiobook.generation_controls import (
    DEFAULT_CLASS_TEMPERATURE,
    DEFAULT_LAYER_PENALTY_FACTOR,
    DEFAULT_POSITION_TEMPERATURE,
    DEFAULT_T_SHIFT,
    OmniVoiceGenerationControls,
)


def test_defaults_match_pinned_mlx_omnivoice_defaults():
    controls = OmniVoiceGenerationControls().validated()
    assert controls.narration_style == "auto"
    assert controls.duration_scale is None
    assert controls.class_temperature == DEFAULT_CLASS_TEMPERATURE == 0.0
    assert controls.position_temperature == DEFAULT_POSITION_TEMPERATURE == 5.0
    assert controls.layer_penalty_factor == DEFAULT_LAYER_PENALTY_FACTOR == 5.0
    assert controls.t_shift == DEFAULT_T_SHIFT == 0.1


def test_controls_validate_safe_bounds():
    controls = OmniVoiceGenerationControls(
        narration_style="audiobook",
        duration_scale=0.9,
        class_temperature=0.2,
        position_temperature=4.0,
        layer_penalty_factor=4.5,
        t_shift=0.12,
    ).validated()
    assert controls.narration_style == "audiobook"
    assert controls.duration_scale == 0.9
    assert "duration_scale=0.9" in controls.cache_signature()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("narration_style", "dramatic"),
        ("duration_scale", 0.5),
        ("duration_scale", 1.5),
        ("class_temperature", -0.1),
        ("class_temperature", 2.1),
        ("position_temperature", -1.0),
        ("position_temperature", 10.1),
        ("layer_penalty_factor", -0.1),
        ("layer_penalty_factor", 10.1),
        ("t_shift", 0.0),
        ("t_shift", 1.1),
    ],
)
def test_invalid_controls_are_rejected(field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError):
        OmniVoiceGenerationControls(**kwargs).validated()


def test_checkpoint_signature_changes_for_every_quality_control():
    baseline = OmniVoiceGenerationControls().cache_signature()
    variants = [
        OmniVoiceGenerationControls(narration_style="neutral"),
        OmniVoiceGenerationControls(narration_style="audiobook"),
        OmniVoiceGenerationControls(duration_scale=0.95),
        OmniVoiceGenerationControls(class_temperature=0.1),
        OmniVoiceGenerationControls(position_temperature=4.5),
        OmniVoiceGenerationControls(layer_penalty_factor=4.0),
        OmniVoiceGenerationControls(t_shift=0.2),
    ]
    assert all(item.cache_signature() != baseline for item in variants)

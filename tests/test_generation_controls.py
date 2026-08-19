from __future__ import annotations

from types import SimpleNamespace

import pytest

from tamil_audiobook.controlled_engine import _ControlledModel
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


class _FakeModel:
    sample_rate = 24000

    def __init__(self):
        self.calls = []

    def generate(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return iter(())


def test_auto_style_preserves_existing_prosody_and_forwards_native_controls():
    fake = _FakeModel()
    controlled = _ControlledModel(
        fake,
        OmniVoiceGenerationControls(
            narration_style="auto",
            class_temperature=0.25,
            position_temperature=4.25,
            layer_penalty_factor=4.75,
            t_shift=0.2,
        ),
    )
    list(controlled.generate(text="Hello?", instruct="Question instruction"))
    kwargs = fake.calls[0][1]
    assert kwargs["instruct"] == "Question instruction"
    assert kwargs["class_temperature"] == 0.25
    assert kwargs["position_temperature"] == 4.25
    assert kwargs["layer_penalty_factor"] == 4.75
    assert kwargs["t_shift"] == 0.2
    assert "duration_s" not in kwargs


def test_neutral_style_disables_semantic_instruction():
    fake = _FakeModel()
    controlled = _ControlledModel(fake, OmniVoiceGenerationControls(narration_style="neutral"))
    list(controlled.generate(text="Hello?", instruct="Question instruction"))
    assert fake.calls[0][1]["instruct"] == "None"


def test_audiobook_style_only_fills_neutral_instruction():
    fake = _FakeModel()
    controlled = _ControlledModel(fake, OmniVoiceGenerationControls(narration_style="audiobook"))
    list(controlled.generate(text="Plain narration.", instruct="None"))
    assert "polished audiobook narration" in fake.calls[0][1]["instruct"]

    fake2 = _FakeModel()
    controlled2 = _ControlledModel(fake2, OmniVoiceGenerationControls(narration_style="audiobook"))
    list(controlled2.generate(text="Question?", instruct="Question instruction"))
    assert fake2.calls[0][1]["instruct"] == "Question instruction"


def test_duration_scale_uses_config_sample_rate_when_model_has_no_direct_attribute(monkeypatch):
    class ConfigOnlyModel:
        config = SimpleNamespace(sample_rate=24000)

        def __init__(self):
            self.calls = []

        def generate(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return iter(())

    captured = {}

    def fake_scaled_duration_seconds(text, *, duration_scale, sample_rate):
        captured.update(text=text, duration_scale=duration_scale, sample_rate=sample_rate)
        return 3.25

    monkeypatch.setattr(
        "tamil_audiobook.controlled_engine.scaled_duration_seconds",
        fake_scaled_duration_seconds,
    )
    fake = ConfigOnlyModel()
    controlled = _ControlledModel(fake, OmniVoiceGenerationControls(duration_scale=0.9))
    list(controlled.generate(text="தமிழ் benchmark sentence."))

    assert captured == {
        "text": "தமிழ் benchmark sentence.",
        "duration_scale": 0.9,
        "sample_rate": 24000,
    }
    assert fake.calls[0][1]["duration_s"] == 3.25

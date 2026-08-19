from __future__ import annotations

from dataclasses import asdict, dataclass

OMNIVOICE_CONTROLS_VERSION = 1

NARRATION_STYLES = ("auto", "neutral", "audiobook")

DEFAULT_CLASS_TEMPERATURE = 0.0
DEFAULT_POSITION_TEMPERATURE = 5.0
DEFAULT_LAYER_PENALTY_FACTOR = 5.0
DEFAULT_T_SHIFT = 0.1


@dataclass(frozen=True)
class OmniVoiceGenerationControls:
    """Validated controls exposed by the pinned MLX OmniVoice implementation.

    ``duration_scale`` is intentionally an engine-level convenience rather than
    a fake ``speed`` parameter. When set, the engine reproduces OmniVoice's own
    rule-based duration estimate and passes a scaled ``duration_s`` to
    ``model.generate``. A value below 1.0 requests shorter/faster speech; a
    value above 1.0 requests longer/slower speech. ``None`` preserves the
    upstream automatic-duration path exactly.
    """

    narration_style: str = "auto"
    duration_scale: float | None = None
    class_temperature: float = DEFAULT_CLASS_TEMPERATURE
    position_temperature: float = DEFAULT_POSITION_TEMPERATURE
    layer_penalty_factor: float = DEFAULT_LAYER_PENALTY_FACTOR
    t_shift: float = DEFAULT_T_SHIFT

    def validated(self) -> "OmniVoiceGenerationControls":
        style = str(self.narration_style or "auto").strip().lower()
        if style not in NARRATION_STYLES:
            raise ValueError(f"narration_style must be one of {', '.join(NARRATION_STYLES)}")

        duration_scale = None if self.duration_scale is None else float(self.duration_scale)
        if duration_scale is not None and not 0.75 <= duration_scale <= 1.35:
            raise ValueError("duration_scale must be between 0.75 and 1.35")

        class_temperature = float(self.class_temperature)
        if not 0.0 <= class_temperature <= 2.0:
            raise ValueError("class_temperature must be between 0.0 and 2.0")

        position_temperature = float(self.position_temperature)
        if not 0.0 <= position_temperature <= 10.0:
            raise ValueError("position_temperature must be between 0.0 and 10.0")

        layer_penalty_factor = float(self.layer_penalty_factor)
        if not 0.0 <= layer_penalty_factor <= 10.0:
            raise ValueError("layer_penalty_factor must be between 0.0 and 10.0")

        t_shift = float(self.t_shift)
        if not 0.02 <= t_shift <= 1.0:
            raise ValueError("t_shift must be between 0.02 and 1.0")

        return OmniVoiceGenerationControls(
            narration_style=style,
            duration_scale=duration_scale,
            class_temperature=class_temperature,
            position_temperature=position_temperature,
            layer_penalty_factor=layer_penalty_factor,
            t_shift=t_shift,
        )

    def as_dict(self) -> dict:
        return asdict(self.validated())

    def cache_signature(self) -> str:
        values = self.as_dict()
        return "|".join(f"{key}={values[key]}" for key in sorted(values))


DEFAULT_OMNIVOICE_CONTROLS = OmniVoiceGenerationControls()


def scaled_duration_seconds(text: str, *, duration_scale: float | None, sample_rate: int) -> float | None:
    """Return a native OmniVoice ``duration_s`` target, or ``None`` for auto.

    This mirrors the exact duration path in mlx-audio 0.4.6:
    ``RuleDurationEstimator(...).estimate_duration(text, 'Nice to meet you.', 25)``
    followed by the 1.15 token multiplier. We then scale that target and convert
    it back to seconds using OmniVoice's 960 samples-per-audio-token contract.
    """
    if duration_scale is None:
        return None
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    from mlx_audio.tts.models.omnivoice.duration import RuleDurationEstimator

    estimator = RuleDurationEstimator()
    raw_tokens = estimator.estimate_duration(str(text or ""), "Nice to meet you.", 25)
    target_tokens = max(10, int(raw_tokens * 1.15))
    tokens_per_second = sample_rate / 960.0
    base_seconds = target_tokens / tokens_per_second
    return max(0.1, base_seconds * float(duration_scale))

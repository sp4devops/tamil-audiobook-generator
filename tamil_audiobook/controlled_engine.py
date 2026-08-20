from __future__ import annotations

from pathlib import Path

from . import engine as base_engine
from .generation_controls import (
    OMNIVOICE_CONTROLS_VERSION,
    OmniVoiceGenerationControls,
    scaled_duration_seconds,
)


class _ControlledModel:
    def __init__(self, model, controls: OmniVoiceGenerationControls):
        self._model = model
        self._controls = controls.validated()

    def __getattr__(self, name):
        return getattr(self._model, name)

    def _sample_rate(self) -> int:
        direct = int(getattr(self._model, "sample_rate", 0) or 0)
        if direct > 0:
            return direct
        config = getattr(self._model, "config", None)
        return int(getattr(config, "sample_rate", 0) or 0)

    def generate(self, *args, **kwargs):
        controls = self._controls
        text = kwargs.get("text")
        if text is None and args:
            text = args[0]

        if controls.narration_style == "neutral":
            kwargs["instruct"] = "None"
        elif controls.narration_style == "audiobook":
            existing = str(kwargs.get("instruct", "None") or "None")
            if existing == "None":
                kwargs["instruct"] = (
                    "Natural polished audiobook narration; clear phrasing, steady pacing, "
                    "restrained expression; keep the same speaker identity."
                )

        duration_s = scaled_duration_seconds(
            str(text or ""),
            duration_scale=controls.duration_scale,
            sample_rate=self._sample_rate(),
        )
        if duration_s is not None:
            kwargs["duration_s"] = duration_s

        kwargs["class_temperature"] = controls.class_temperature
        kwargs["position_temperature"] = controls.position_temperature
        kwargs["layer_penalty_factor"] = controls.layer_penalty_factor
        kwargs["t_shift"] = controls.t_shift
        return self._model.generate(*args, **kwargs)


def synthesize_audiobook_with_controls(
    *,
    controls: OmniVoiceGenerationControls | None = None,
    **kwargs,
) -> dict:
    """Run the production engine with validated OmniVoice controls.

    P7 uses explicit model-loader and checkpoint-signature injection instead of
    temporarily monkey-patching module globals. This is thread-safe and keeps
    one generation job from leaking controls into another caller.
    """
    selected = (controls or OmniVoiceGenerationControls()).validated()
    signature = selected.cache_signature()

    from mlx_audio.tts.utils import load_model

    def controlled_load_model(*args, **load_kwargs):
        return _ControlledModel(load_model(*args, **load_kwargs), selected)

    report = base_engine.synthesize_audiobook(
        **kwargs,
        model_loader=controlled_load_model,
        checkpoint_salt=f"controls-v{OMNIVOICE_CONTROLS_VERSION}|{signature}",
    )

    report["omnivoice_controls_version"] = OMNIVOICE_CONTROLS_VERSION
    report["omnivoice_controls"] = selected.as_dict()
    report["native_speed_parameter"] = False
    report["duration_control"] = (
        "automatic" if selected.duration_scale is None else "native_duration_s_scaled"
    )

    report_path = kwargs.get("report_path")
    if report_path is not None:
        import json

        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report

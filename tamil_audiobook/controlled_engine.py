from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

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
            sample_rate=int(getattr(self._model, "sample_rate", 0) or 0),
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
    """Run the production engine with validated, opt-in OmniVoice controls.

    The accepted engine defaults are preserved when ``controls`` is omitted or
    left at defaults. Checkpoint identity is extended with the control signature
    so audio created with one parameter set is never silently reused for another.
    """
    selected = (controls or OmniVoiceGenerationControls()).validated()
    signature = selected.cache_signature()

    from mlx_audio.tts import utils as tts_utils

    original_load_model: Callable = tts_utils.load_model
    original_checkpoint_key: Callable = base_engine._checkpoint_key

    def controlled_load_model(*args, **load_kwargs):
        return _ControlledModel(original_load_model(*args, **load_kwargs), selected)

    def controlled_checkpoint_key(**key_kwargs):
        original = original_checkpoint_key(**key_kwargs)
        digest = hashlib.sha256()
        digest.update(original.encode("ascii"))
        digest.update(b"\0")
        digest.update(f"controls-v{OMNIVOICE_CONTROLS_VERSION}|{signature}".encode("utf-8"))
        return digest.hexdigest()

    tts_utils.load_model = controlled_load_model
    base_engine._checkpoint_key = controlled_checkpoint_key
    try:
        report = base_engine.synthesize_audiobook(**kwargs)
    finally:
        base_engine._checkpoint_key = original_checkpoint_key
        tts_utils.load_model = original_load_model

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

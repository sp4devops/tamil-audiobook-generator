from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def omnivoice_quality_mode():
    """Let OmniVoice estimate output duration instead of forcing planner timings.

    ListenLeaf still keeps its own duration estimates for UI/ETA purposes. Those
    estimates must never be passed as hard synthesis durations because Tamil and
    mixed-language chunks can require substantially more speech time, leading to
    rushed output, skipped words, and garbling.
    """
    from mlx_audio.tts.models.omnivoice.omnivoice import Model

    original_generate = Model.generate

    def quality_generate(self, *args, **kwargs):
        kwargs.pop("duration_s", None)
        return original_generate(self, *args, **kwargs)

    Model.generate = quality_generate
    try:
        yield
    finally:
        Model.generate = original_generate

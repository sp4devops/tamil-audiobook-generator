from __future__ import annotations

_INSTALLED = False


def install_omnivoice_quality_mode() -> bool:
    """Stop ListenLeaf planner estimates from becoming hard TTS durations.

    The UI still uses estimated durations for ETA. OmniVoice itself is allowed to
    estimate the actual target length, preventing dense Tamil/mixed chunks from
    being compressed into too little audio and dropping or garbling words.
    """
    global _INSTALLED
    if _INSTALLED:
        return False

    from mlx_audio.tts.models.omnivoice.omnivoice import Model

    original_generate = Model.generate
    if getattr(original_generate, "_listenleaf_quality_mode", False):
        _INSTALLED = True
        return False

    def quality_generate(self, *args, **kwargs):
        kwargs.pop("duration_s", None)
        return original_generate(self, *args, **kwargs)

    quality_generate._listenleaf_quality_mode = True
    quality_generate._listenleaf_original_generate = original_generate
    Model.generate = quality_generate
    _INSTALLED = True
    return True

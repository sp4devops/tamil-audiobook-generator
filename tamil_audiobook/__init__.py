"""Local Tamil/English audiobook generation package."""

from .quality_mode import install_omnivoice_quality_mode

# Install once at package import so every CLI/UI synthesis path lets OmniVoice
# estimate target speech duration instead of forcing ListenLeaf's rough ETA.
install_omnivoice_quality_mode()

from .engine import (
    DEFAULT_CROSSFADE_MS,
    DEFAULT_NUM_STEPS,
    chunk_text,
    detect_language,
    estimate_duration_seconds,
    synthesize_audiobook,
)

__all__ = [
    "DEFAULT_CROSSFADE_MS",
    "DEFAULT_NUM_STEPS",
    "chunk_text",
    "detect_language",
    "estimate_duration_seconds",
    "synthesize_audiobook",
]

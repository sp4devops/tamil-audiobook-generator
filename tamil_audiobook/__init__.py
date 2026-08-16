"""Local Tamil/English audiobook generation package."""

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

from __future__ import annotations

import re
from dataclasses import dataclass

PROSODY_VERSION = 1

_LIST_RE = re.compile(r"^(?:[-*•]\s+|\d{1,3}[.)]\s+)")
_HEADING_RE = re.compile(
    r"^(?:chapter|part|section|book|அத்தியாயம்|பகுதி)\b",
    re.IGNORECASE,
)
_DIALOGUE_RE = re.compile(r'^(?:["“‘]|[—–-]\s+)')


@dataclass(frozen=True)
class ProsodyProfile:
    name: str
    instruct: str


_NEUTRAL = ProsodyProfile("neutral", "None")
_PROFILES = {
    "dialogue": ProsodyProfile(
        "dialogue",
        "Natural conversational audiobook dialogue; restrained expression; keep the same speaker identity.",
    ),
    "question": ProsodyProfile(
        "question",
        "Natural questioning intonation for audiobook narration; restrained expression; keep the same speaker identity.",
    ),
    "exclamation": ProsodyProfile(
        "exclamation",
        "Slightly emphatic audiobook delivery; restrained expression; keep the same speaker identity.",
    ),
    "heading": ProsodyProfile(
        "heading",
        "Clear deliberate audiobook heading; calm emphasis; keep the same speaker identity.",
    ),
    "list": ProsodyProfile(
        "list",
        "Clear enumerated audiobook delivery; even pacing; keep the same speaker identity.",
    ),
}


def prosody_for_chunk(text: str, boundary: str) -> ProsodyProfile:
    """Return a conservative OmniVoice instruction for an explicit narration role.

    Ordinary prose intentionally stays on ``instruct='None'`` so the accepted
    P2 narration remains the baseline. Role instructions are only applied when
    the text itself or its punctuation provides a strong signal.
    """
    stripped = str(text or "").strip()
    if not stripped:
        return _NEUTRAL
    if _HEADING_RE.match(stripped) and len(stripped.split()) <= 12:
        return _PROFILES["heading"]
    if _LIST_RE.match(stripped):
        return _PROFILES["list"]
    if _DIALOGUE_RE.match(stripped):
        return _PROFILES["dialogue"]
    normalized_boundary = str(boundary or "continuation")
    if normalized_boundary == "question":
        return _PROFILES["question"]
    if normalized_boundary == "exclamation":
        return _PROFILES["exclamation"]
    return _NEUTRAL

from __future__ import annotations

import re
from dataclasses import dataclass

PROSODY_VERSION = 2

_LIST_RE = re.compile(r"^(?:[-*•]\s+|\d{1,3}[.)]\s+)")
_HEADING_RE = re.compile(
    r"^(?:chapter|part|section|book|அத்தியாயம்|பகுதி)\b",
    re.IGNORECASE,
)
_DIALOGUE_RE = re.compile(r'^(?:["“‘]|[—–-]\s+)')
_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")

# High-signal conversational markers only. These are deliberately conservative:
# they should trigger a natural spoken delivery without turning formal prose into
# exaggerated acting.
_TAMIL_CONVERSATIONAL = (
    "மச்சி", "மச்சான்", "டா", "டி", "டேய்", "என்னடா", "என்னங்க", "ஆமா",
    "இல்ல", "இருக்கு", "இருக்கா", "பண்ணு", "பண்ணுங்க", "பண்ணலாம்", "பண்ணலாமா",
    "செம", "ரொம்ப", "சரி விடு", "அப்பாடா", "பாத்தியா", "வாங்க", "போய்ட்டு",
)
_TANGLISH_CONVERSATIONAL = {
    "machi", "machan", "da", "dei", "enna", "ennada", "aama", "ama", "illa",
    "irukku", "iruka", "romba", "seri", "sari", "pannu", "pannunga", "pannalaam",
    "paathiya", "semma", "appadi", "apdi", "epdi", "eppadi", "venum", "venam",
}


@dataclass(frozen=True)
class ProsodyProfile:
    name: str
    instruct: str


_NEUTRAL = ProsodyProfile("neutral", "None")
_PROFILES = {
    "dialogue": ProsodyProfile(
        "dialogue",
        "Natural conversational audiobook dialogue; speak as one continuous thought, with realistic Tamil/English rhythm; restrained expression; keep the same speaker identity.",
    ),
    "question": ProsodyProfile(
        "question",
        "Natural questioning intonation for audiobook narration; emphasize the contrast or doubt without overacting; keep the same speaker identity.",
    ),
    "exclamation": ProsodyProfile(
        "exclamation",
        "Slightly emphatic audiobook delivery; lively but controlled, with natural emphasis and no shouting; keep the same speaker identity.",
    ),
    "heading": ProsodyProfile(
        "heading",
        "Clear deliberate audiobook heading; calm emphasis; keep the same speaker identity.",
    ),
    "list": ProsodyProfile(
        "list",
        "Clear enumerated audiobook delivery; even pacing; keep the same speaker identity.",
    ),
    "tamil-conversational": ProsodyProfile(
        "tamil-conversational",
        "Natural everyday spoken Tamil; warm, lively and locally conversational, with smooth phrase flow and colloquial rhythm; avoid formal newsreader cadence and avoid exaggerated acting; keep the same speaker identity.",
    ),
    "tanglish-conversational": ProsodyProfile(
        "tanglish-conversational",
        "Natural Tamil-English Tanglish conversation; preserve Tamil rhythm around English words, make code-switches seamless, and keep a lively but restrained native conversational flow; keep the same speaker identity.",
    ),
    "mixed-conversational": ProsodyProfile(
        "mixed-conversational",
        "Natural bilingual Tamil-English audiobook speech; keep code-switches inside one continuous phrase, preserve Tamil conversational rhythm around English terms, and avoid a voice or accent reset at language boundaries; keep the same speaker identity.",
    ),
}


def _contains_tamil_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _TAMIL_CONVERSATIONAL)


def _contains_tanglish_marker(text: str) -> bool:
    words = {match.group(0).lower().strip("'-") for match in _LATIN_WORD_RE.finditer(text)}
    return bool(words & _TANGLISH_CONVERSATIONAL)


def _conversational_profile(text: str) -> ProsodyProfile | None:
    has_tamil = bool(_TAMIL_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))
    tamil_marker = _contains_tamil_marker(text)
    tanglish_marker = _contains_tanglish_marker(text)

    if has_tamil and has_latin and (tamil_marker or tanglish_marker):
        return _PROFILES["mixed-conversational"]
    if has_tamil and tamil_marker:
        return _PROFILES["tamil-conversational"]
    if not has_tamil and has_latin and tanglish_marker:
        return _PROFILES["tanglish-conversational"]
    return None


def prosody_for_chunk(text: str, boundary: str) -> ProsodyProfile:
    """Return a conservative OmniVoice instruction for the current speech unit.

    P5 keeps formal narration on the accepted neutral baseline, but no longer
    treats obvious colloquial Tamil/Tanglish as formal prose. High-signal spoken
    markers receive a restrained conversational instruction so native rhythm and
    code-switch continuity can be expressed by OmniVoice without changing the
    accepted speaker identity settings.
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

    # Explicit punctuation intent remains authoritative over a conversational
    # style hint. A colloquial question still needs question intonation.
    normalized_boundary = str(boundary or "continuation")
    if normalized_boundary == "question":
        return _PROFILES["question"]
    if normalized_boundary == "exclamation":
        return _PROFILES["exclamation"]

    conversational = _conversational_profile(stripped)
    if conversational is not None:
        return conversational
    return _NEUTRAL

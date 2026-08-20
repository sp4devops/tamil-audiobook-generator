from __future__ import annotations

import re
from dataclasses import dataclass

PROSODY_VERSION = 6

_LIST_RE = re.compile(r"^(?:[-*•]\s+|\d{1,3}[.)]\s+)")
_HEADING_RE = re.compile(r"^(?:chapter|part|section|book|அத்தியாயம்|பகுதி)\b", re.IGNORECASE)
_DIALOGUE_RE = re.compile(r'^(?:["“‘]|[—–-]\s+)')
_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_TAMIL_TOKEN_RE = re.compile(r"[\u0B80-\u0BFF]+")
_LATIN_RE = re.compile(r"[A-Za-z]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")

_TAMIL_CONVERSATIONAL = (
    "மச்சி", "மச்சான்", "டா", "டி", "டேய்", "என்னடா", "என்னங்க", "ஆமா",
    "இல்ல", "இருக்கு", "இருக்கா", "பண்ணு", "பண்ணுங்க", "பண்ணலாம்", "பண்ணலாமா",
    "செம", "ரொம்ப", "சரி விடு", "அப்பாடா", "பாத்தியா", "வாங்க", "போய்ட்டு",
)
_TANGLISH_CONVERSATIONAL = {
    "machi", "machan", "da", "dei", "enna", "ennada", "aama", "ama", "illa",
    "irukku", "iruka", "romba", "seri", "sari", "pannu", "pannunga", "pannalaam",
    "panna", "pannidu", "pannitu", "paathiya", "semma", "appadi", "apdi", "epdi",
    "eppadi", "venum", "venam", "intha", "indha", "aaguma", "eduthuttu", "varen",
}


@dataclass(frozen=True)
class ProsodyProfile:
    name: str
    instruct: str


_NEUTRAL = ProsodyProfile("neutral", "None")
_PACE_CONTINUITY = (
    "Match the surrounding Tamil speaking rate. Do not speed up, clip, or compress embedded English words or "
    "Tamil-script English loanwords; give them the same relaxed syllabic timing as the surrounding Tamil."
)
_INDIAN_CODE_SWITCH = (
    "Keep one South-Indian Tamil bilingual speaker throughout. Pronounce embedded English words in natural "
    "South-Indian English, with everyday Indian-English stress and rhythm. Do not switch into an American or "
    "British accent at English words, and do not over-Tamilize technical English. Keep English words clear while "
    "preserving the surrounding Tamil phrase rhythm and the same speaker identity. " + _PACE_CONTINUITY
)
_INDIAN_ENGLISH_CONTINUATION = (
    "Continue as the same South-Indian Tamil bilingual speaker from the surrounding passage. Speak this English "
    "in natural everyday South-Indian English with Indian-English stress and rhythm. Do not reset into an American "
    "or British accent, do not imitate a separate English narrator, and keep the same timbre and conversational energy. "
    + _PACE_CONTINUITY
)

_PROFILES = {
    "dialogue": ProsodyProfile("dialogue", "Natural conversational audiobook dialogue; speak as one continuous thought, with realistic Tamil/English rhythm; restrained expression; keep the same speaker identity."),
    "question": ProsodyProfile("question", "Natural questioning intonation for audiobook narration; emphasize the contrast or doubt without overacting; keep the same speaker identity."),
    "exclamation": ProsodyProfile("exclamation", "Slightly emphatic audiobook delivery; lively but controlled, with natural emphasis and no shouting; keep the same speaker identity."),
    "heading": ProsodyProfile("heading", "Clear deliberate audiobook heading; calm emphasis; keep the same speaker identity."),
    "list": ProsodyProfile("list", "Clear enumerated audiobook delivery; even pacing; keep the same speaker identity."),
    "tamil-conversational": ProsodyProfile("tamil-conversational", "Natural everyday spoken Tamil; warm, lively and locally conversational, with smooth phrase flow and colloquial rhythm; avoid formal newsreader cadence and avoid exaggerated acting; keep the same speaker identity. " + _PACE_CONTINUITY),
    "tanglish-conversational": ProsodyProfile("tanglish-conversational", "Natural Tamil-English Tanglish conversation; preserve Tamil sentence rhythm and a lively but restrained native conversational flow. " + _INDIAN_CODE_SWITCH),
    "mixed-conversational": ProsodyProfile("mixed-conversational", "Natural bilingual Tamil-English speech; keep every code-switch inside one continuous Tamil phrase. " + _INDIAN_CODE_SWITCH),
    "mixed-dialogue": ProsodyProfile("mixed-dialogue", "Natural conversational Tamil-English dialogue; follow the punctuation and emotion naturally without acting or changing persona. " + _INDIAN_CODE_SWITCH),
    "mixed-question": ProsodyProfile("mixed-question", "Natural Tamil-English questioning intonation; keep the Tamil question contour and emphasize contrast or doubt without overacting. " + _INDIAN_CODE_SWITCH),
    "mixed-exclamation": ProsodyProfile("mixed-exclamation", "Lively but controlled Tamil-English exclamation; preserve the Tamil conversational cadence and do not shout. " + _INDIAN_CODE_SWITCH),
    "indian-english-continuation": ProsodyProfile("indian-english-continuation", _INDIAN_ENGLISH_CONTINUATION),
    "indian-english-dialogue": ProsodyProfile("indian-english-dialogue", "Natural conversational dialogue with restrained expression. " + _INDIAN_ENGLISH_CONTINUATION),
    "indian-english-question": ProsodyProfile("indian-english-question", "Use natural questioning intonation and clear contrast without overacting. " + _INDIAN_ENGLISH_CONTINUATION),
    "indian-english-exclamation": ProsodyProfile("indian-english-exclamation", "Use lively but controlled emphasis without shouting. " + _INDIAN_ENGLISH_CONTINUATION),
}


def _tamil_tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _TAMIL_TOKEN_RE.finditer(text))


def _contains_tamil_marker(text: str) -> bool:
    """Match complete Tamil lexical tokens/phrases, never arbitrary substrings."""
    tokens = _tamil_tokens(text)
    if not tokens:
        return False
    single = {marker for marker in _TAMIL_CONVERSATIONAL if " " not in marker}
    if any(token in single for token in tokens):
        return True
    joined = " ".join(tokens)
    for marker in _TAMIL_CONVERSATIONAL:
        if " " in marker and re.search(rf"(?:^| ){re.escape(marker)}(?: |$)", joined):
            return True
    return False


def _contains_tanglish_marker(text: str) -> bool:
    words = {match.group(0).lower().strip("'-") for match in _LATIN_WORD_RE.finditer(text)}
    return bool(words & _TANGLISH_CONVERSATIONAL)


def _code_switch_delivery(text: str) -> bool:
    has_tamil = bool(_TAMIL_RE.search(text)); has_latin = bool(_LATIN_RE.search(text))
    if has_tamil and has_latin: return True
    return not has_tamil and has_latin and _contains_tanglish_marker(text)


def _tamil_bilingual_frame(text: str) -> bool:
    return bool(text) and (bool(_TAMIL_RE.search(text)) or _contains_tanglish_marker(text))


def _pure_english(text: str) -> bool:
    return bool(_LATIN_RE.search(text)) and not bool(_TAMIL_RE.search(text)) and not _contains_tanglish_marker(text)


def _conversational_profile(text: str) -> ProsodyProfile | None:
    has_tamil = bool(_TAMIL_RE.search(text)); has_latin = bool(_LATIN_RE.search(text))
    tamil_marker = _contains_tamil_marker(text); tanglish_marker = _contains_tanglish_marker(text)
    if has_tamil and has_latin and (tamil_marker or tanglish_marker): return _PROFILES["mixed-conversational"]
    if has_tamil and tamil_marker: return _PROFILES["tamil-conversational"]
    if not has_tamil and has_latin and tanglish_marker: return _PROFILES["tanglish-conversational"]
    return None


def prosody_for_chunk(text: str, boundary: str, *, previous_text: str = "", next_text: str = "") -> ProsodyProfile:
    stripped = str(text or "").strip()
    if not stripped: return _NEUTRAL
    code_switch = _code_switch_delivery(stripped)
    contextual_english = _pure_english(stripped) and (_tamil_bilingual_frame(previous_text) or _tamil_bilingual_frame(next_text))
    if _HEADING_RE.match(stripped) and len(stripped.split()) <= 12 and not contextual_english: return _PROFILES["heading"]
    if _LIST_RE.match(stripped) and not contextual_english: return _PROFILES["list"]
    if _DIALOGUE_RE.match(stripped):
        if code_switch: return _PROFILES["mixed-dialogue"]
        if contextual_english: return _PROFILES["indian-english-dialogue"]
        return _PROFILES["dialogue"]
    normalized_boundary = str(boundary or "continuation")
    if normalized_boundary == "question":
        if code_switch: return _PROFILES["mixed-question"]
        if contextual_english: return _PROFILES["indian-english-question"]
        return _PROFILES["question"]
    if normalized_boundary == "exclamation":
        if code_switch: return _PROFILES["mixed-exclamation"]
        if contextual_english: return _PROFILES["indian-english-exclamation"]
        return _PROFILES["exclamation"]
    if contextual_english: return _PROFILES["indian-english-continuation"]
    conversational = _conversational_profile(stripped)
    return conversational if conversational is not None else _NEUTRAL

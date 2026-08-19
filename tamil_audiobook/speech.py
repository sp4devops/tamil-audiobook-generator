from __future__ import annotations

import re
from dataclasses import dataclass

_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_PARAGRAPH_RE = re.compile(r"\n\s*\n+")
_SENTENCE_RE = re.compile(r"(?<=[.!?।])\s+")
_CLAUSE_RE = re.compile(r"(?<=[,;:—–])\s+")

# High-signal colloquial Tamil words commonly written in Latin script.  This is
# intentionally conservative: ordinary English prose must not be relabelled as
# Tamil just because it contains a short ambiguous token such as "in" or "or".
_TANGLISH_WORDS = {
    "aama", "ama", "aiyo", "aiyyo", "apdi", "appadi", "avan", "ava", "avanga",
    "da", "dei", "enna", "epdi", "eppadi", "inga", "illa", "illai", "irukku",
    "iruka", "irukkaa", "machan", "machi", "mama", "mapla", "na", "naan", "namma",
    "nee", "neenga", "pa", "paathiya", "pannu", "pannunga", "pannala", "pannitu",
    "poda", "podi", "poitu", "romba", "seri", "sari", "semma", "solra", "sonna",
    "thaan", "than", "vara", "vandhu", "venam", "venum", "ya", "yen", "yenga",
}

_TANGLISH_SUFFIXES = (
    "nga", "nunga", "anum", "kku", "ukku", "la", "le", "lam", "rom",
    "raan", "raanga", "ranga", "rathu", "ttan", "tten", "ttu", "thaan",
)

# These markers are intentionally small and high-signal. They are used only
# while splitting already-long sentences, never as a general language model.
_SEMANTIC_CONNECTORS = (
    "ஆனால்", "ஆனா", "அதனால்", "எனவே", "ஆகவே", "பின்னர்", "பிறகு",
    "இருந்தாலும்", "என்றாலும்", "மேலும்", "அதே சமயம்", "ஏனெனில்",
    "but", "however", "therefore", "meanwhile", "although", "though",
    "because", "instead", "yet", "so", "then", "also",
    "aana", "ana", "athanala", "appuram",
)
_STRONG_SEMANTIC_SHIFTS = (
    "ஆனால்", "ஆனா", "இருந்தாலும்", "என்றாலும்", "அதே சமயம்",
    "but", "however", "meanwhile", "although", "though", "instead", "yet",
    "aana", "ana",
)

_CONNECTOR_PATTERN = "|".join(
    re.escape(item) for item in sorted(_SEMANTIC_CONNECTORS, key=len, reverse=True)
)
_SEMANTIC_SPLIT_RE = re.compile(
    rf"\s+(?=(?:{_CONNECTOR_PATTERN})(?=$|[\s,;:]))",
    re.IGNORECASE,
)
_LIST_RE = re.compile(r"^(?:[-*•]\s+|\d{1,3}[.)]\s+)")
_HEADING_RE = re.compile(
    r"^(?:chapter|part|section|book|அத்தியாயம்|பகுதி)\b",
    re.IGNORECASE,
)
_DIALOGUE_RE = re.compile(r'^(?:["“‘]|[—–-]\s+)')

_TARGET_PROSODY_SECONDS = 8.5
_MAX_PROSODY_SECONDS = 10.5


@dataclass(frozen=True)
class SpeechUnit:
    text: str
    language: str
    profile: str
    estimated_seconds: float
    boundary: str


@dataclass(frozen=True)
class _RawUnit:
    text: str
    paragraph_end: bool
    role: str
    boundary_override: str = ""
    planned_break: bool = False


def _latin_words(text: str) -> list[str]:
    return [match.group(0).lower().strip("'-") for match in _LATIN_WORD_RE.finditer(text)]


def looks_tanglish(text: str) -> bool:
    """Return True for high-confidence romanized conversational Tamil."""
    words = _latin_words(text)
    if not words:
        return False
    known = sum(word in _TANGLISH_WORDS for word in words)
    morphology = sum(
        len(word) >= 5 and any(word.endswith(suffix) for suffix in _TANGLISH_SUFFIXES)
        for word in words
    )
    if known >= 2:
        return True
    if known >= 1 and morphology >= 1:
        return True
    return known >= 1 and len(words) <= 4


def classify_language(text: str) -> tuple[str, str]:
    """Return the OmniVoice language value and a diagnostic speech profile."""
    tamil_chars = len(_TAMIL_RE.findall(text))
    latin_chars = sum(ch.isalpha() and ord(ch) < 128 for ch in text)
    if tamil_chars and latin_chars:
        return "None", "mixed-script"
    if tamil_chars:
        return "tamil", "tamil"
    if looks_tanglish(text):
        return "None", "tanglish"
    return "english", "english"


def _speech_rate(profile: str) -> float:
    return 2.0 if profile in {"tamil", "mixed-script", "tanglish"} else 2.4


def _prosodic_seconds(text: str, profile: str | None = None) -> float:
    if profile is None:
        _, profile = classify_language(text)
    return max(0.5, len(text.split()) / _speech_rate(profile))


def estimate_spoken_seconds(text: str, profile: str | None = None) -> float:
    if profile is None:
        _, profile = classify_language(text)
    # Preserve the established engine contract used by progress estimates.
    return float(min(12.0, max(3.0, _prosodic_seconds(text, profile))))


def _hard_split(text: str, max_chars: int) -> list[str]:
    words = text.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(word[i:i + max_chars] for i in range(0, len(word), max_chars))
            continue
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _balanced_word_split(text: str, target_chars: int, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    if any(len(word) > max_chars for word in words):
        return _hard_split(text, max_chars)

    pieces: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        _, profile = classify_language(candidate)
        too_long = (
            len(candidate) > max_chars
            or _prosodic_seconds(candidate, profile) > _MAX_PROSODY_SECONDS
        )
        target_reached = (
            current
            and len(candidate) > target_chars
            and len(current) >= max(24, int(target_chars * 0.55))
        )
        if current and (too_long or target_reached):
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)

    safe: list[str] = []
    for piece in pieces:
        safe.extend(_hard_split(piece, max_chars) if len(piece) > max_chars else [piece])
    return safe


def _strip_leading_wrappers(text: str) -> str:
    return text.lstrip(' \t"\'“”‘’([{—–-').strip()


def _starts_with_any(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = _strip_leading_wrappers(text).lower()
    for phrase in phrases:
        marker = phrase.lower()
        if normalized == marker:
            return True
        if normalized.startswith(marker + " ") or normalized.startswith(marker + ","):
            return True
    return False


def _starts_semantic_connector(text: str) -> bool:
    return _starts_with_any(text, _SEMANTIC_CONNECTORS)


def _starts_strong_shift(text: str) -> bool:
    return _starts_with_any(text, _STRONG_SEMANTIC_SHIFTS)


def _semantic_segments(sentence: str) -> list[str]:
    clauses = [part.strip() for part in _CLAUSE_RE.split(sentence) if part.strip()]
    segments: list[str] = []
    for clause in clauses or [sentence]:
        parts = [part.strip() for part in _SEMANTIC_SPLIT_RE.split(clause) if part.strip()]
        segments.extend(parts or [clause])
    return segments


def _pack_semantic_segments(
    segments: list[str],
    *,
    target_chars: int,
    max_chars: int,
) -> list[str]:
    expanded: list[str] = []
    for segment in segments:
        _, profile = classify_language(segment)
        if (
            len(segment) > max_chars
            or _prosodic_seconds(segment, profile) > _MAX_PROSODY_SECONDS
        ):
            expanded.extend(_balanced_word_split(segment, target_chars, max_chars))
        else:
            expanded.append(segment)

    pieces: list[str] = []
    current = ""
    for segment in expanded:
        candidate = f"{current} {segment}".strip()
        _, profile = classify_language(candidate)
        candidate_seconds = _prosodic_seconds(candidate, profile)
        if not current:
            current = segment
            continue
        if len(candidate) <= target_chars and candidate_seconds <= _TARGET_PROSODY_SECONDS:
            current = candidate
            continue
        if (
            len(current) < max(24, int(target_chars * 0.55))
            and len(candidate) <= max_chars
            and candidate_seconds <= _MAX_PROSODY_SECONDS
        ):
            current = candidate
            continue
        pieces.append(current)
        current = segment
    if current:
        pieces.append(current)
    return pieces


def _sentence_pieces(sentence: str, target_chars: int, max_chars: int) -> list[str]:
    _, profile = classify_language(sentence)
    if (
        len(sentence) <= max_chars
        and _prosodic_seconds(sentence, profile) <= _MAX_PROSODY_SECONDS
    ):
        return [sentence]

    segments = _semantic_segments(sentence)
    if len(segments) > 1:
        return _pack_semantic_segments(
            segments,
            target_chars=target_chars,
            max_chars=max_chars,
        )
    return _balanced_word_split(sentence, target_chars, max_chars)


def _line_role(line: str) -> str:
    stripped = line.strip()
    if _LIST_RE.match(stripped):
        return "list"
    if _DIALOGUE_RE.match(stripped):
        return "dialogue"
    if _HEADING_RE.match(stripped) and len(stripped.split()) <= 12:
        return "heading"
    return "narration"


def _boundary_kind(
    text: str,
    *,
    paragraph_end: bool = False,
    override: str = "",
) -> str:
    if paragraph_end:
        return "paragraph"
    if override:
        return override
    stripped = text.rstrip('"\'”’)]}')
    if stripped.endswith("?"):
        return "question"
    if stripped.endswith("!"):
        return "exclamation"
    if stripped.endswith((".", "।")):
        return "sentence"
    if stripped.endswith((";", ":")):
        return "clause-strong"
    if stripped.endswith(","):
        return "clause"
    return "continuation"


def _profile(text: str) -> str:
    return classify_language(text)[1]


def _can_merge(
    previous: _RawUnit,
    current: _RawUnit,
    target_chars: int,
    max_chars: int,
) -> bool:
    if previous.paragraph_end or current.planned_break:
        return False
    if previous.role != current.role or previous.role in {"list", "heading"}:
        return False
    previous_boundary = _boundary_kind(
        previous.text,
        paragraph_end=previous.paragraph_end,
        override=previous.boundary_override,
    )
    if previous_boundary in {"question", "exclamation", "clause-strong"}:
        return False
    if _profile(previous.text) != _profile(current.text):
        return False

    candidate = f"{previous.text} {current.text}".strip()
    if len(candidate) > max_chars:
        return False
    profile = _profile(candidate)
    if _prosodic_seconds(candidate, profile) > _MAX_PROSODY_SECONDS:
        return False

    if previous_boundary == "sentence":
        soft_limit = min(
            max_chars,
            max(target_chars + 28, int(target_chars * 1.18)),
        )
        return len(candidate) <= soft_limit

    return len(candidate) <= min(
        max_chars,
        max(target_chars + 20, int(target_chars * 1.15)),
    )


def plan_speech_units(
    text: str,
    *,
    target_chars: int = 140,
    max_chars: int = 220,
) -> list[SpeechUnit]:
    """Split book text into semantic, prosodically useful OmniVoice requests.

    P2 keeps paragraphs authoritative, preserves dialogue/list turns, avoids
    coalescing across language-profile changes, and balances oversized sentences
    around semantic breath groups instead of greedily filling the hard limit.
    """
    if target_chars <= 0 or max_chars < target_chars:
        raise ValueError("invalid chunk size limits")
    cleaned = re.sub(r"[ \t]+", " ", text.strip())
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in _PARAGRAPH_RE.split(cleaned) if part.strip()]
    raw_units: list[_RawUnit] = []

    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()] or [paragraph]
        for line_index, line in enumerate(lines):
            role = _line_role(line)
            sentences = [part.strip() for part in _SENTENCE_RE.split(line) if part.strip()] or [line]
            for sentence_index, sentence in enumerate(sentences):
                pieces = _sentence_pieces(sentence, target_chars, max_chars)
                for piece_index, piece in enumerate(pieces):
                    final_piece = piece_index == len(pieces) - 1
                    final_sentence = sentence_index == len(sentences) - 1
                    final_line = line_index == len(lines) - 1
                    paragraph_end = final_piece and final_sentence and final_line

                    boundary_override = ""
                    if not final_piece:
                        next_piece = pieces[piece_index + 1]
                        if _starts_strong_shift(next_piece):
                            boundary_override = "clause-strong"
                        elif _starts_semantic_connector(next_piece):
                            boundary_override = "clause"
                    elif (
                        final_sentence
                        and not final_line
                        and role in {"dialogue", "list", "heading"}
                        and _boundary_kind(piece) == "continuation"
                    ):
                        # A physical line break is a fallback turn boundary only.
                        # Preserve stronger punctuation such as ? / ! / . so the
                        # P1 pause engine keeps the intended prosody.
                        boundary_override = "sentence"

                    raw_units.append(
                        _RawUnit(
                            text=piece,
                            paragraph_end=paragraph_end,
                            role=role,
                            boundary_override=boundary_override,
                            planned_break=len(pieces) > 1,
                        )
                    )

    merged: list[_RawUnit] = []
    for unit in raw_units:
        if merged and _can_merge(merged[-1], unit, target_chars, max_chars):
            previous = merged[-1]
            merged[-1] = _RawUnit(
                text=f"{previous.text} {unit.text}".strip(),
                paragraph_end=unit.paragraph_end,
                role=unit.role,
                boundary_override=unit.boundary_override,
                planned_break=previous.planned_break,
            )
        else:
            merged.append(unit)

    planned: list[SpeechUnit] = []
    for unit in merged:
        language, profile = classify_language(unit.text)
        planned.append(
            SpeechUnit(
                text=unit.text,
                language=language,
                profile=profile,
                estimated_seconds=estimate_spoken_seconds(unit.text, profile),
                boundary=_boundary_kind(
                    unit.text,
                    paragraph_end=unit.paragraph_end,
                    override=unit.boundary_override,
                ),
            )
        )
    return planned

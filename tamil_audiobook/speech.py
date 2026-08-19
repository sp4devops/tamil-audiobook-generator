from __future__ import annotations

import re
from dataclasses import dataclass

_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_PARAGRAPH_RE = re.compile(r"\n\s*\n+")
_SENTENCE_RE = re.compile(r"(?<=[.!?।])\s+|\n+")
_CLAUSE_RE = re.compile(r"(?<=[,;:])\s+")

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
    "nga", "nunga", "anum", "anum", "kku", "ukku", "la", "le", "lam", "rom",
    "raan", "raanga", "ranga", "rathu", "rathu", "ttan", "tten", "ttu", "thaan",
)


@dataclass(frozen=True)
class SpeechUnit:
    text: str
    language: str
    profile: str
    estimated_seconds: float
    boundary: str


def _latin_words(text: str) -> list[str]:
    return [match.group(0).lower().strip("'-") for match in _LATIN_WORD_RE.finditer(text)]


def looks_tanglish(text: str) -> bool:
    """Return True for high-confidence romanized conversational Tamil.

    The detector is lexical rather than a generic "Indian English" detector. It
    deliberately needs either multiple known colloquial tokens or one known
    token plus Tamil-like morphology so normal English text remains English.
    """
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
        # OmniVoice's None mode is preferable for romanized Tamil because
        # forcing English can pull pronunciation toward English phonotactics.
        return "None", "tanglish"
    return "english", "english"


def estimate_spoken_seconds(text: str, profile: str | None = None) -> float:
    words = max(1, len(text.split()))
    if profile is None:
        _, profile = classify_language(text)
    rate = 2.0 if profile in {"tamil", "mixed-script", "tanglish"} else 2.4
    # Preserve the established engine contract: estimates stay in the same
    # 3-12 second envelope used by progress reporting and acceptance tests.
    return float(min(12.0, max(3.0, words / rate)))


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


def _boundary_kind(text: str, *, paragraph_end: bool = False) -> str:
    if paragraph_end:
        return "paragraph"
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


def plan_speech_units(
    text: str,
    *,
    target_chars: int = 140,
    max_chars: int = 220,
) -> list[SpeechUnit]:
    """Split book text into speakable units rather than arbitrary character blocks.

    Paragraphs and sentences are authoritative boundaries.  Oversized sentences
    prefer comma/semicolon/colon breath groups before falling back to word-safe
    hard splitting. Short adjacent sentences may still share one TTS request to
    preserve discourse flow without exceeding the existing model-safe limits.
    """
    if target_chars <= 0 or max_chars < target_chars:
        raise ValueError("invalid chunk size limits")
    cleaned = re.sub(r"[ \t]+", " ", text.strip())
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in _PARAGRAPH_RE.split(cleaned) if part.strip()]
    raw_units: list[tuple[str, bool]] = []
    for paragraph in paragraphs:
        sentences = [part.strip() for part in _SENTENCE_RE.split(paragraph) if part.strip()]
        if not sentences:
            sentences = [paragraph]
        for sentence_index, sentence in enumerate(sentences):
            paragraph_end = sentence_index == len(sentences) - 1
            if len(sentence) <= max_chars:
                raw_units.append((sentence, paragraph_end))
                continue
            clauses = [part.strip() for part in _CLAUSE_RE.split(sentence) if part.strip()]
            if len(clauses) == 1:
                pieces = _hard_split(sentence, max_chars)
            else:
                pieces = []
                current = ""
                for clause in clauses:
                    candidate = f"{current} {clause}".strip()
                    if current and len(candidate) > max_chars:
                        pieces.append(current)
                        current = clause
                    elif len(clause) > max_chars:
                        if current:
                            pieces.append(current)
                            current = ""
                        pieces.extend(_hard_split(clause, max_chars))
                    else:
                        current = candidate
                if current:
                    pieces.append(current)
            for piece_index, piece in enumerate(pieces):
                raw_units.append((piece, paragraph_end and piece_index == len(pieces) - 1))

    # Preserve natural paragraph/sentence boundaries but coalesce very short
    # continuation units when doing so gives the model more prosodic context.
    merged: list[tuple[str, bool]] = []
    for unit, paragraph_end in raw_units:
        if not merged:
            merged.append((unit, paragraph_end))
            continue
        previous, previous_paragraph_end = merged[-1]
        candidate = f"{previous} {unit}".strip()
        previous_boundary = _boundary_kind(previous, paragraph_end=previous_paragraph_end)
        can_merge = (
            not previous_paragraph_end
            and previous_boundary not in {"question", "exclamation"}
            and len(previous) < target_chars
            and len(candidate) <= max_chars
        )
        if can_merge:
            merged[-1] = (candidate, paragraph_end)
        else:
            merged.append((unit, paragraph_end))

    planned: list[SpeechUnit] = []
    for unit, paragraph_end in merged:
        language, profile = classify_language(unit)
        planned.append(
            SpeechUnit(
                text=unit,
                language=language,
                profile=profile,
                estimated_seconds=estimate_spoken_seconds(unit, profile),
                boundary=_boundary_kind(unit, paragraph_end=paragraph_end),
            )
        )
    return planned

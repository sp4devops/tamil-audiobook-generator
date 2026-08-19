from __future__ import annotations

import re
import unicodedata

_TAMIL_DEPENDENT = set(chr(code) for code in range(0x0BBE, 0x0BCD + 1)) | {"\u0BD7"}
_TAMIL_PREBASE = {"\u0BC6", "\u0BC7", "\u0BC8"}  # ெ ே ை
_TAMIL_BLOCK = range(0x0B80, 0x0C00)
_ZERO_WIDTH_JUNK = {"\u200b", "\ufeff", "\u2060"}
_HORIZONTAL_SPACE = {" ", "\t", "\u00a0"}
_TAMIL_RUN_RE = re.compile(r"[\u0B80-\u0BFF]+")


def _is_tamil(ch: str) -> bool:
    return bool(ch) and ord(ch) in _TAMIL_BLOCK


def _is_tamil_letter(ch: str) -> bool:
    return _is_tamil(ch) and unicodedata.category(ch).startswith("L")


def _previous_nonspace(chars: list[str], index: int) -> str:
    i = index - 1
    while i >= 0 and chars[i] in _HORIZONTAL_SPACE:
        i -= 1
    return chars[i] if i >= 0 else ""


def _next_nonspace(chars: list[str], index: int) -> tuple[int, str]:
    i = index + 1
    while i < len(chars) and chars[i] in _HORIZONTAL_SPACE:
        i += 1
    return i, chars[i] if i < len(chars) else ""


def _looks_visual_order(text: str) -> bool:
    """Detect one Tamil word/run extracted in visual glyph order.

    Correct Unicode Tamil stores E/EE/AI signs after their base consonant. A
    visually ordered PDF word exposes at least one such sign before a Tamil base
    without a Tamil letter immediately before it. Detection is deliberately
    scoped to a contiguous Tamil run so a damaged word cannot cause a valid word
    such as ``கேளுங்கள்`` elsewhere on the same line to be rewritten.
    """
    chars = list(text)
    candidates = 0
    suspicious = 0
    for i, ch in enumerate(chars):
        if ch not in _TAMIL_PREBASE:
            continue
        _, nxt = _next_nonspace(chars, i)
        if not _is_tamil_letter(nxt):
            continue
        candidates += 1
        prev = _previous_nonspace(chars, i)
        if not _is_tamil_letter(prev):
            suspicious += 1
    return suspicious > 0 and suspicious / max(1, candidates) >= 0.20


def _repair_visual_order_word(text: str) -> str:
    if not _looks_visual_order(text):
        return text

    # Once a single contiguous Tamil word is positively identified as visual
    # order, all pre-base signs in that word belong before the following glyph.
    # Moving each sign after that glyph reconstructs logical Unicode order. This
    # handles words such as ``ேநயர்கேள`` -> ``நேயர்களே`` while leaving a valid
    # ``கேளுங்கள்`` untouched because that word does not trigger detection.
    chars = list(text)
    out: list[str] = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch in _TAMIL_PREBASE:
            j, nxt = _next_nonspace(chars, i)
            if _is_tamil_letter(nxt):
                out.append(nxt)
                out.append(ch)
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _repair_visual_order_run(text: str) -> str:
    return _TAMIL_RUN_RE.sub(lambda match: _repair_visual_order_word(match.group(0)), text)


def _repair_visual_order(text: str) -> str:
    # PDF encodings can differ between embedded fonts/pages and even between
    # words on one line. Repair each contiguous Tamil word independently.
    return "\n".join(_repair_visual_order_run(line) for line in text.split("\n"))


def normalize_book_text(text: str) -> str:
    """Repair Unicode damage introduced by Tamil PDF text extraction.

    The routine preserves already-correct Tamil. It removes extraction-only
    dotted-circle/zero-width artefacts, detects words encoded in visual glyph
    order, restores Unicode logical order, reconnects dependent signs separated
    by horizontal PDF spacing and returns NFC text for both browser display and
    TTS input.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch not in _ZERO_WIDTH_JUNK)
    text = text.replace("\u25cc", "")
    text = _repair_visual_order(text)

    out: list[str] = []
    for ch in text:
        if ch in _TAMIL_DEPENDENT:
            spaces: list[str] = []
            while out and out[-1] in _HORIZONTAL_SPACE:
                spaces.append(out.pop())
            if out and _is_tamil(out[-1]):
                out.append(ch)
            else:
                out.extend(reversed(spaces))
                out.append(ch)
        else:
            out.append(ch)

    repaired = unicodedata.normalize("NFC", "".join(out))
    repaired = re.sub(r"[ \t\u00a0]+", " ", repaired)
    repaired = re.sub(r" *\n *", "\n", repaired)
    return repaired.strip()

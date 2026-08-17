from __future__ import annotations

import re
import unicodedata

# Tamil dependent vowel signs, virama and length mark. These must follow a
# Tamil base character in Unicode logical order. Some PDFs store the visual
# glyph order instead, especially for the left-side signs E/EE/AI, producing
# strings such as "ேந..." instead of "நே...". Browsers render an orphan sign
# with a dotted circle and TTS receives the same malformed sequence.
_TAMIL_DEPENDENT = set(chr(code) for code in range(0x0BBE, 0x0BCD + 1)) | {"\u0BD7"}
_TAMIL_PREBASE = {"\u0BC6", "\u0BC7", "\u0BC8"}  # ெ ே ை
_TAMIL_BLOCK = range(0x0B80, 0x0C00)
_ZERO_WIDTH_JUNK = {"\u200b", "\ufeff", "\u2060"}
_HORIZONTAL_SPACE = {" ", "\t", "\u00a0"}


def _is_tamil(ch: str) -> bool:
    return bool(ch) and ord(ch) in _TAMIL_BLOCK


def _is_tamil_letter(ch: str) -> bool:
    return _is_tamil(ch) and unicodedata.category(ch).startswith("L")


def _repair_visual_order(text: str) -> str:
    """Move visually preposed Tamil vowel signs behind their base letter.

    PDF text extraction can emit the glyph order `ே` + `ந` although Unicode
    requires `ந` + `ே`. We only reorder E/EE/AI signs when immediately followed
    (allowing horizontal PDF spacing) by a Tamil letter. NFC then composes
    combinations such as க + ெ + ா -> கொ, க + ே + ா -> கோ and
    க + ெ + ௗ -> கௌ.
    """
    chars = list(text)
    out: list[str] = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch in _TAMIL_PREBASE:
            j = i + 1
            while j < len(chars) and chars[j] in _HORIZONTAL_SPACE:
                j += 1
            if j < len(chars) and _is_tamil_letter(chars[j]):
                base = chars[j]
                out.append(base)
                out.append(ch)
                i = j + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def normalize_book_text(text: str) -> str:
    """Repair conservative Unicode damage introduced by PDF text extraction.

    This does not transliterate or rewrite vocabulary. It repairs Unicode order,
    removes extraction-only dotted-circle/zero-width artefacts, and reconnects
    dependent Tamil signs that were separated from their base by horizontal
    whitespace. The returned text is NFC-normalized for both browser display and
    TTS input.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch not in _ZERO_WIDTH_JUNK)
    # U+25CC DOTTED CIRCLE is a rendering aid, not book content.
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

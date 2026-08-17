from __future__ import annotations

import re
import unicodedata

# Tamil dependent vowel signs, virama and length mark. These must follow a
# Tamil base character; PDF extraction sometimes inserts whitespace/dotted
# circles between the base and sign, which both browsers and TTS interpret as
# an orphan mark.
_TAMIL_DEPENDENT = set(chr(code) for code in range(0x0BBE, 0x0BCD + 1)) | {"\u0BD7"}
_TAMIL_BLOCK = range(0x0B80, 0x0C00)
_ZERO_WIDTH_JUNK = {"\u200b", "\ufeff", "\u2060"}


def _is_tamil(ch: str) -> bool:
    return bool(ch) and ord(ch) in _TAMIL_BLOCK


def normalize_book_text(text: str) -> str:
    """Conservatively repair Unicode damage commonly introduced by PDF text extraction.

    The function does not transliterate or rewrite Tamil words. It only removes
    extraction artefacts and restores dependent Tamil signs to the preceding
    Tamil character when whitespace/dotted-circle placeholders split them.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch not in _ZERO_WIDTH_JUNK)
    # U+25CC DOTTED CIRCLE is a rendering aid frequently copied from broken PDFs.
    text = text.replace("\u25cc", "")

    out: list[str] = []
    for ch in text:
        if ch in _TAMIL_DEPENDENT:
            # If extraction separated a dependent sign from its base only by
            # horizontal whitespace, reattach it. Never cross punctuation/newlines.
            spaces: list[str] = []
            while out and out[-1] in {" ", "\t", "\u00a0"}:
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

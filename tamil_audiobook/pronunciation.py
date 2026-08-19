from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_OVERRIDES = {
    "Kubernetes": "Kubernetes",
    "MongoDB": "Mongo D B",
    "PostgreSQL": "Post gres Q L",
    "API": "A P I",
    "APIs": "A P I s",
    "CPU": "C P U",
    "GPU": "G P U",
    "RAM": "RAM",
    "MLX": "M L X",
    "OmniVoice": "Omni Voice",
}

# Safe, high-confidence Romanized Tamil normalizations. The replacement is only
# sent to the TTS model; the book text and read-along text remain unchanged.
# Converting common colloquial tokens to Tamil script avoids the English-token
# pronunciation bias that makes Tanglish sound foreign or mechanical.
_TANGLISH_NORMALIZATIONS = {
    "machi": "மச்சி",
    "machan": "மச்சான்",
    "dei": "டேய்",
    "da": "டா",
    "enna": "என்ன",
    "ennada": "என்னடா",
    "aama": "ஆமா",
    "ama": "ஆமா",
    "illa": "இல்ல",
    "illai": "இல்லை",
    "irukku": "இருக்கு",
    "iruka": "இருக்கா",
    "irukkaa": "இருக்கா",
    "romba": "ரொம்ப",
    "seri": "சரி",
    "sari": "சரி",
    "pannu": "பண்ணு",
    "pannunga": "பண்ணுங்க",
    "pannalaam": "பண்ணலாம்",
    "pannalam": "பண்ணலாம்",
    "paathiya": "பாத்தியா",
    "semma": "செம",
    "apdi": "அப்படி",
    "appadi": "அப்படி",
    "epdi": "எப்படி",
    "eppadi": "எப்படி",
    "naan": "நான்",
    "nee": "நீ",
    "neenga": "நீங்க",
    "namma": "நம்ம",
    "inga": "இங்க",
    "yen": "ஏன்",
    "venum": "வேணும்",
    "venam": "வேணாம்",
    "appuram": "அப்புறம்",
    "poitu": "போய்ட்டு",
    "vandhu": "வந்து",
}

# Hyphen is intentionally excluded from the ASCII token. That lets a base term
# still match when Tamil morphology is attached, for example API-ஐ, server-ல,
# MongoDB-க்கு. The suffix and punctuation are preserved by the regex engine.
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9.+#_]*)(?![A-Za-z0-9_])")


@dataclass(frozen=True)
class PronunciationResult:
    text: str
    applied: tuple[str, ...]


def default_override_path() -> Path:
    root = Path(os.environ.get("TAMIL_AUDIOBOOK_HOME", "~/.tamil_audiobook")).expanduser()
    return root / "pronunciation.json"


def load_overrides(path: Path | None = None) -> dict[str, str]:
    overrides = dict(_DEFAULT_OVERRIDES)
    source = path if path is not None else default_override_path()
    if not source.is_file():
        return overrides
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pronunciation overrides must be a JSON object")
    for raw_source, spoken in payload.items():
        if not isinstance(raw_source, str) or not raw_source.strip():
            raise ValueError("pronunciation override keys must be non-empty strings")
        if not isinstance(spoken, str) or not spoken.strip():
            raise ValueError(f"pronunciation override for {raw_source!r} must be a non-empty string")
        overrides[raw_source] = spoken.strip()
    return overrides


def override_signature(overrides: dict[str, str]) -> str:
    payload = json.dumps(
        {
            "overrides": overrides,
            "tanglish_normalizations": _TANGLISH_NORMALIZATIONS,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_pronunciation_overrides(text: str, overrides: dict[str, str] | None = None) -> PronunciationResult:
    mapping = overrides if overrides is not None else _DEFAULT_OVERRIDES
    if not text:
        return PronunciationResult(text=text, applied=())

    folded_mapping = {key.casefold(): value for key, value in mapping.items()}
    applied: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        spoken = mapping.get(token)
        if spoken is None:
            spoken = folded_mapping.get(token.casefold())
        if spoken is not None:
            if spoken != token:
                applied.append(token)
            return spoken

        normalized = _TANGLISH_NORMALIZATIONS.get(token.casefold())
        if normalized is not None:
            applied.append(token)
            return normalized
        return token

    rendered = _TOKEN_RE.sub(replace, text)
    return PronunciationResult(text=rendered, applied=tuple(applied))

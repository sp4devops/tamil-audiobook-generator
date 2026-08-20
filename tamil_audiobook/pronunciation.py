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

# High-confidence Romanized Tamil normalizations. These replacements are only
# sent to the TTS model; source/read-along text remains unchanged. P7 applies
# them inside mixed-script chunks too, but only when the token is explicitly in
# this conservative lexicon. Ordinary English words are never transliterated.
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
    "panna": "பண்ண",
    "pannunga": "பண்ணுங்க",
    "pannalaam": "பண்ணலாம்",
    "pannalam": "பண்ணலாம்",
    "pannidu": "பண்ணிடு",
    "pannitu": "பண்ணிட்டு",
    "pannittu": "பண்ணிட்டு",
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
    "intha": "இந்த",
    "indha": "இந்த",
    "yen": "ஏன்",
    "venum": "வேணும்",
    "venam": "வேணாம்",
    "appuram": "அப்புறம்",
    "poitu": "போய்ட்டு",
    "vandhu": "வந்து",
    "eduthuttu": "எடுத்துட்டு",
    "eduthitu": "எடுத்துட்டு",
    "varen": "வரேன்",
    "varren": "வரேன்",
    "aaguma": "ஆகுமா",
    "aagum": "ஆகும்",
    "aachu": "ஆச்சு",
    "kulla": "குள்ள",
    "konjam": "கொஞ்சம்",
    "mudinjutha": "முடிஞ்சுதா",
    "mudinjuthu": "முடிஞ்சுது",
    "nu": "னு",
}

# Single weak tokens like "da", "ama", "sari" can occur in non-Tanglish text.
# In an all-Latin chunk we normalize only when there are multiple known tokens
# or at least one strong conversational marker. Tamil-script context is already
# an unambiguous signal, so known Romanized Tamil tokens are safe there.
_STRONG_TANGLISH_TOKENS = {
    "machi", "machan", "dei", "ennada", "irukku", "iruka", "irukkaa", "romba",
    "pannu", "panna", "pannunga", "pannalaam", "pannalam", "pannidu", "pannitu",
    "paathiya", "semma", "apdi", "appadi", "epdi", "eppadi", "neenga", "namma",
    "intha", "indha", "venum", "venam", "appuram", "poitu", "vandhu", "eduthuttu",
    "aaguma", "aachu", "mudinjutha", "mudinjuthu",
}

_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
# Keep internal technical dots (Node.js, v1.2.3) while excluding trailing
# sentence punctuation so tokens such as "machi." still hit the Tanglish map.
_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z](?:[A-Za-z0-9+#_]*[A-Za-z0-9+#_])?(?:\.[A-Za-z0-9+#_]+)*)(?![A-Za-z0-9_])"
)


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
            "tanglish_policy": "context-aware-mixed-script-v2",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tanglish_normalization_enabled(text: str) -> bool:
    if _TAMIL_RE.search(text):
        return True
    tokens = [match.group(1).casefold() for match in _TOKEN_RE.finditer(text)]
    known = [token for token in tokens if token in _TANGLISH_NORMALIZATIONS]
    return len(known) >= 2 or any(token in _STRONG_TANGLISH_TOKENS for token in known)


def apply_pronunciation_overrides(text: str, overrides: dict[str, str] | None = None) -> PronunciationResult:
    mapping = overrides if overrides is not None else _DEFAULT_OVERRIDES
    if not text:
        return PronunciationResult(text=text, applied=())

    folded_mapping = {key.casefold(): value for key, value in mapping.items()}
    applied: list[str] = []
    normalize_tanglish = _tanglish_normalization_enabled(text)

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        spoken = mapping.get(token)
        if spoken is None:
            spoken = folded_mapping.get(token.casefold())
        if spoken is not None:
            if spoken != token:
                applied.append(token)
            return spoken

        if normalize_tanglish:
            normalized = _TANGLISH_NORMALIZATIONS.get(token.casefold())
            if normalized is not None:
                applied.append(token)
                return normalized
        return token

    rendered = _TOKEN_RE.sub(replace, text)
    return PronunciationResult(text=rendered, applied=tuple(applied))

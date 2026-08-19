from __future__ import annotations

import json
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

_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9.+#_-]*)(?![A-Za-z0-9_])")


@dataclass(frozen=True)
class PronunciationResult:
    text: str
    applied: tuple[str, ...]


def load_overrides(path: Path | None = None) -> dict[str, str]:
    overrides = dict(_DEFAULT_OVERRIDES)
    if path is None or not path.is_file():
        return overrides
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pronunciation overrides must be a JSON object")
    for source, spoken in payload.items():
        if not isinstance(source, str) or not source.strip():
            raise ValueError("pronunciation override keys must be non-empty strings")
        if not isinstance(spoken, str) or not spoken.strip():
            raise ValueError(f"pronunciation override for {source!r} must be a non-empty string")
        overrides[source] = spoken.strip()
    return overrides


def apply_pronunciation_overrides(text: str, overrides: dict[str, str] | None = None) -> PronunciationResult:
    mapping = overrides or _DEFAULT_OVERRIDES
    if not text or not mapping:
        return PronunciationResult(text=text, applied=())
    applied: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        spoken = mapping.get(token)
        if spoken is None:
            return token
        if spoken != token:
            applied.append(token)
        return spoken

    rendered = _TOKEN_RE.sub(replace, text)
    return PronunciationResult(text=rendered, applied=tuple(applied))

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

_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9.+#_-]*)(?![A-Za-z0-9_])")


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
    payload = json.dumps(overrides, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_pronunciation_overrides(text: str, overrides: dict[str, str] | None = None) -> PronunciationResult:
    mapping = overrides if overrides is not None else _DEFAULT_OVERRIDES
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

from __future__ import annotations

import json
import math
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import soundfile as sf

MODEL_ID = "mlx-community/OmniVoice-bf16"
DEFAULT_NUM_STEPS = 20
DEFAULT_GUIDANCE_SCALE = 2.5
DEFAULT_CROSSFADE_MS = 55
DEFAULT_TARGET_CHARS = 140
DEFAULT_MAX_CHARS = 220

_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+|(?<=\u0B83)\s+|\n+")


@dataclass(frozen=True)
class Chunk:
    text: str
    language: str
    estimated_seconds: float


def detect_language(text: str) -> str:
    tamil_chars = len(_TAMIL_RE.findall(text))
    latin_chars = sum(ch.isalpha() and ord(ch) < 128 for ch in text)
    if tamil_chars and latin_chars:
        return "None"
    if tamil_chars:
        return "tamil"
    return "english"


def estimate_duration_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    tamil_chars = len(_TAMIL_RE.findall(text))
    if tamil_chars:
        seconds = words / 2.0
    else:
        seconds = words / 2.4
    return float(min(12.0, max(3.0, seconds)))


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"[ \t]+", " ", text.strip())
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]
    return parts or [cleaned]


def chunk_text(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    if target_chars <= 0 or max_chars < target_chars:
        raise ValueError("invalid chunk size limits")

    chunks: list[str] = []
    current = ""
    for sentence in _sentences(text):
        if len(sentence) > max_chars:
            words = sentence.split()
            piece = ""
            for word in words:
                candidate = f"{piece} {word}".strip()
                if piece and len(candidate) > max_chars:
                    chunks.append(piece)
                    piece = word
                else:
                    piece = candidate
            if piece:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(piece)
            continue

        candidate = f"{current} {sentence}".strip()
        if current and (len(candidate) > max_chars or len(current) >= target_chars):
            chunks.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        chunks.append(current)

    return [
        Chunk(text=item, language=detect_language(item), estimated_seconds=estimate_duration_seconds(item))
        for item in chunks
    ]


def _to_numpy(audio) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def _crossfade_join(parts: Iterable[np.ndarray], sample_rate: int, crossfade_ms: int) -> np.ndarray:
    arrays = [np.asarray(part, dtype=np.float32).reshape(-1) for part in parts if len(part)]
    if not arrays:
        return np.zeros(0, dtype=np.float32)
    result = arrays[0].copy()
    fade_samples = max(0, int(sample_rate * crossfade_ms / 1000))
    for nxt in arrays[1:]:
        n = min(fade_samples, len(result), len(nxt))
        if n <= 0:
            result = np.concatenate([result, nxt])
            continue
        fade_out = np.linspace(1.0, 0.0, n, endpoint=False, dtype=np.float32)
        fade_in = 1.0 - fade_out
        overlap = result[-n:] * fade_out + nxt[:n] * fade_in
        result = np.concatenate([result[:-n], overlap, nxt[n:]])
    return result


def _write_mp3(wav_path: Path, mp3_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(mp3_path),
        ],
        check=True,
    )


def synthesize_audiobook(
    *,
    text: str,
    reference_audio: Path,
    reference_text: str,
    output_wav: Path,
    output_mp3: Path | None = None,
    num_steps: int = DEFAULT_NUM_STEPS,
    guidance_scale: float = DEFAULT_GUIDANCE_SCALE,
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
    target_chars: int = DEFAULT_TARGET_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
    report_path: Path | None = None,
) -> dict:
    if not reference_audio.is_file():
        raise FileNotFoundError(reference_audio)
    if not reference_text.strip():
        raise ValueError("reference text is empty")
    if guidance_scale <= 0:
        raise ValueError("guidance_scale must be positive")
    chunks = chunk_text(text, target_chars=target_chars, max_chars=max_chars)
    if not chunks:
        raise ValueError("input text is empty")

    from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt
    from mlx_audio.tts.utils import load_model

    load_started = time.perf_counter()
    model = load_model(MODEL_ID)
    model_load_seconds = time.perf_counter() - load_started

    prompt_started = time.perf_counter()
    ref_tokens = create_voice_clone_prompt(
        str(reference_audio), tokenizer=model.audio_tokenizer, ref_text=reference_text
    )
    prompt_encode_seconds = time.perf_counter() - prompt_started
    if getattr(ref_tokens, "size", 0) == 0:
        raise RuntimeError("empty clone-reference tokens")

    generated_parts: list[np.ndarray] = []
    chunk_reports: list[dict] = []
    sample_rate: int | None = None
    generation_started = time.perf_counter()

    for index, chunk in enumerate(chunks):
        started = time.perf_counter()
        results = list(
            model.generate(
                text=chunk.text,
                language=chunk.language,
                ref_tokens=ref_tokens,
                ref_text=reference_text,
                duration_s=chunk.estimated_seconds,
                num_steps=num_steps,
                guidance_scale=guidance_scale,
            )
        )
        elapsed = time.perf_counter() - started
        if not results:
            raise RuntimeError(f"no audio returned for chunk {index}")
        result = results[-1]
        audio = _to_numpy(result.audio)
        current_rate = int(
            getattr(result, "sample_rate", 0) or getattr(model, "sample_rate", 0)
        )
        if current_rate <= 0 or not len(audio) or not np.isfinite(audio).all():
            raise RuntimeError(f"invalid audio for chunk {index}")
        if sample_rate is None:
            sample_rate = current_rate
        elif sample_rate != current_rate:
            raise RuntimeError("sample rate changed between chunks")
        generated_parts.append(audio)
        seconds = len(audio) / current_rate
        chunk_reports.append(
            {
                "index": index,
                "language": chunk.language,
                "chars": len(chunk.text),
                "generation_seconds": round(elapsed, 3),
                "audio_seconds": round(seconds, 3),
                "rtf": round(elapsed / seconds, 4),
            }
        )

    generation_seconds = time.perf_counter() - generation_started
    assert sample_rate is not None
    joined = _crossfade_join(generated_parts, sample_rate, crossfade_ms)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_wav, joined, sample_rate)
    if output_mp3 is not None:
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        _write_mp3(output_wav, output_mp3)

    audio_seconds = len(joined) / sample_rate
    report = {
        "status": "PASS",
        "engine": "OmniVoice-MLX",
        "model_id": MODEL_ID,
        "num_steps": num_steps,
        "guidance_scale": guidance_scale,
        "crossfade_ms": crossfade_ms,
        "chunks": len(chunks),
        "model_load_seconds": round(model_load_seconds, 3),
        "prompt_encode_seconds_one_time": round(prompt_encode_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "audio_seconds": round(audio_seconds, 3),
        "aggregate_rtf": round(generation_seconds / audio_seconds, 4),
        "chunk_reports": chunk_reports,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report

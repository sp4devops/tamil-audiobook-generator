from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import soundfile as sf

MODEL_ID = "mlx-community/OmniVoice-bfloat16"
# Immutable Hugging Face revision containing the published bfloat16 weights.
MODEL_REVISION = "c19bf70730272a96dfc3f38d29f59b92c2e8b554"
ENGINE_CACHE_VERSION = 3
DEFAULT_NUM_STEPS = 20
DEFAULT_GUIDANCE_SCALE = 2.5
DEFAULT_CROSSFADE_MS = 55
DEFAULT_TARGET_CHARS = 140
DEFAULT_MAX_CHARS = 220
DEFAULT_ESTIMATE_RTF = 1.55
DEFAULT_ESTIMATE_STARTUP_SECONDS = 20.0

GENERATION_MODE_PAUSE_SECONDS = {"fast": 0.0, "balanced": 2.0, "cool": 5.0}
DEFAULT_GENERATION_MODE = os.environ.get("LISTENLEAF_GENERATION_MODE", "balanced").strip().lower()
if DEFAULT_GENERATION_MODE not in GENERATION_MODE_PAUSE_SECONDS:
    DEFAULT_GENERATION_MODE = "balanced"

_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+|(?<=\u0B83)\s+|\n+")


@dataclass(frozen=True)
class Chunk:
    text: str
    language: str
    estimated_seconds: float


def generation_pause_seconds(mode: str) -> float:
    normalized = str(mode or "").strip().lower()
    if normalized not in GENERATION_MODE_PAUSE_SECONDS:
        raise ValueError(f"generation_mode must be one of {', '.join(GENERATION_MODE_PAUSE_SECONDS)}")
    return GENERATION_MODE_PAUSE_SECONDS[normalized]


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
    seconds = words / (2.0 if tamil_chars else 2.4)
    return float(min(12.0, max(3.0, seconds)))


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"[ \t]+", " ", text.strip())
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]
    return parts or [cleaned]


def _split_long_token(token: str, max_chars: int) -> list[str]:
    return [token[index:index + max_chars] for index in range(0, len(token), max_chars)]


def chunk_text(text: str, *, target_chars: int = DEFAULT_TARGET_CHARS, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    if target_chars <= 0 or max_chars < target_chars:
        raise ValueError("invalid chunk size limits")
    chunks: list[str] = []
    current = ""
    for sentence in _sentences(text):
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sentence.split()
            piece = ""
            for word in words:
                word_parts = _split_long_token(word, max_chars) if len(word) > max_chars else [word]
                for part in word_parts:
                    candidate = f"{piece} {part}".strip()
                    if piece and len(candidate) > max_chars:
                        chunks.append(piece)
                        piece = part
                    elif not piece and len(part) == max_chars:
                        chunks.append(part)
                    else:
                        piece = candidate
            if piece:
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
    return [Chunk(text=item, language=detect_language(item), estimated_seconds=estimate_duration_seconds(item)) for item in chunks]


def estimate_audiobook(
    text: str,
    *,
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
    target_chars: int = DEFAULT_TARGET_CHARS,
    max_chars: int = DEFAULT_MAX_CHARS,
    estimate_rtf: float = DEFAULT_ESTIMATE_RTF,
    startup_seconds: float = DEFAULT_ESTIMATE_STARTUP_SECONDS,
    generation_mode: str = DEFAULT_GENERATION_MODE,
) -> dict:
    chunks = chunk_text(text, target_chars=target_chars, max_chars=max_chars)
    pause_seconds = generation_pause_seconds(generation_mode)
    if not chunks:
        return {"chunks": 0, "audio_seconds": 0.0, "generation_seconds": 0.0, "generation_mode": generation_mode, "thermal_pause_seconds": pause_seconds}
    raw_audio_seconds = sum(chunk.estimated_seconds for chunk in chunks)
    overlap = max(0, len(chunks) - 1) * max(0, crossfade_ms) / 1000.0
    audio_seconds = max(0.0, raw_audio_seconds - overlap)
    thermal_idle_seconds = pause_seconds * max(0, len(chunks) - 1)
    generation_seconds = max(0.0, startup_seconds + audio_seconds * max(0.1, estimate_rtf) + thermal_idle_seconds)
    return {
        "chunks": len(chunks),
        "audio_seconds": round(audio_seconds, 1),
        "generation_seconds": round(generation_seconds, 1),
        "estimate_rtf": estimate_rtf,
        "generation_mode": generation_mode,
        "thermal_pause_seconds": pause_seconds,
        "estimated_thermal_idle_seconds": round(thermal_idle_seconds, 1),
    }


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
    temp_path = mp3_path.with_name(mp3_path.name + ".tmp.mp3")
    temp_path.unlink(missing_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "128k", str(temp_path)], check=True)
        if not temp_path.is_file() or temp_path.stat().st_size < 1000:
            raise RuntimeError("ffmpeg produced an invalid MP3")
        os.replace(temp_path, mp3_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _mlx_audio_version() -> str:
    try:
        return importlib.metadata.version("mlx-audio")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _checkpoint_key(*, text: str, reference_audio: Path, reference_text: str, num_steps: int, guidance_scale: float, crossfade_ms: int, target_chars: int, max_chars: int) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8")); digest.update(b"\0")
    digest.update(reference_text.encode("utf-8")); digest.update(b"\0")
    digest.update(reference_audio.read_bytes())
    digest.update((f"cache={ENGINE_CACHE_VERSION}|model={MODEL_ID}@{MODEL_REVISION}|mlx-audio={_mlx_audio_version()}|steps={num_steps}|guidance={guidance_scale}|crossfade={crossfade_ms}|target={target_chars}|max={max_chars}").encode("utf-8"))
    return digest.hexdigest()


def _prepare_checkpoint_dir(checkpoint_dir: Path, key: str, total_chunks: int) -> int:
    manifest_path = checkpoint_dir / "manifest.json"
    current = None
    try:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not current or current.get("key") != key or int(current.get("total_chunks", -1)) != total_chunks:
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({"key": key, "total_chunks": total_chunks, "cache_version": ENGINE_CACHE_VERSION, "model_id": MODEL_ID, "model_revision": MODEL_REVISION, "mlx_audio_version": _mlx_audio_version()}, indent=2), encoding="utf-8")
    else:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
    contiguous = 0
    for index in range(total_chunks):
        path = checkpoint_dir / f"chunk_{index:05d}.flac"
        if not path.is_file() or path.stat().st_size < 256:
            break
        try:
            info = sf.info(path)
            if info.frames <= 0 or info.samplerate <= 0 or info.channels != 1:
                break
        except Exception:
            break
        contiguous += 1
    return contiguous


def _write_checkpoint(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp.flac")
    temp_path.unlink(missing_ok=True)
    try:
        sf.write(temp_path, audio, sample_rate, format="FLAC", subtype="PCM_16")
        info = sf.info(temp_path)
        if info.frames <= 0 or info.samplerate != sample_rate or info.channels != 1:
            raise RuntimeError(f"invalid temporary checkpoint {path.name}")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _write_stream_part(writer: sf.SoundFile, pending_tail: np.ndarray | None, audio: np.ndarray, fade_samples: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if pending_tail is None:
        if fade_samples > 0 and len(audio) > fade_samples:
            writer.write(audio[:-fade_samples]); return audio[-fade_samples:].copy()
        return audio.copy()
    n = min(fade_samples, len(pending_tail), len(audio)) if fade_samples > 0 else 0
    if n <= 0:
        writer.write(pending_tail)
        if fade_samples > 0 and len(audio) > fade_samples:
            writer.write(audio[:-fade_samples]); return audio[-fade_samples:].copy()
        return audio.copy()
    if len(pending_tail) > n:
        writer.write(pending_tail[:-n])
    fade_out = np.linspace(1.0, 0.0, n, endpoint=False, dtype=np.float32)
    fade_in = 1.0 - fade_out
    writer.write(pending_tail[-n:] * fade_out + audio[:n] * fade_in)
    remainder = audio[n:]
    if len(remainder) > fade_samples:
        writer.write(remainder[:-fade_samples]); return remainder[-fade_samples:].copy()
    return remainder.copy()


def synthesize_audiobook(
    *, text: str, reference_audio: Path, reference_text: str, output_wav: Path,
    output_mp3: Path | None = None, num_steps: int = DEFAULT_NUM_STEPS,
    guidance_scale: float = DEFAULT_GUIDANCE_SCALE, crossfade_ms: int = DEFAULT_CROSSFADE_MS,
    target_chars: int = DEFAULT_TARGET_CHARS, max_chars: int = DEFAULT_MAX_CHARS,
    report_path: Path | None = None, progress_callback: Callable[[dict], None] | None = None,
    checkpoint_dir: Path | None = None, generation_mode: str = DEFAULT_GENERATION_MODE,
) -> dict:
    if not reference_audio.is_file(): raise FileNotFoundError(reference_audio)
    if not reference_text.strip(): raise ValueError("reference text is empty")
    if guidance_scale <= 0: raise ValueError("guidance_scale must be positive")
    pause_seconds = generation_pause_seconds(generation_mode)
    chunks = chunk_text(text, target_chars=target_chars, max_chars=max_chars)
    if not chunks: raise ValueError("input text is empty")
    total_started = time.perf_counter()

    def progress(**payload) -> None:
        if progress_callback is not None:
            payload.setdefault("elapsed_seconds", round(time.perf_counter() - total_started, 1))
            payload.setdefault("generation_mode", generation_mode)
            payload.setdefault("thermal_pause_seconds", pause_seconds)
            progress_callback(payload)

    cached_prefix = 0
    if checkpoint_dir is not None:
        key = _checkpoint_key(text=text, reference_audio=reference_audio, reference_text=reference_text, num_steps=num_steps, guidance_scale=guidance_scale, crossfade_ms=crossfade_ms, target_chars=target_chars, max_chars=max_chars)
        cached_prefix = _prepare_checkpoint_dir(checkpoint_dir, key, len(chunks))
    missing_chunks = []
    for index in range(len(chunks)):
        checkpoint = checkpoint_dir / f"chunk_{index:05d}.flac" if checkpoint_dir is not None else None
        if checkpoint is None or not checkpoint.is_file() or checkpoint.stat().st_size < 256:
            missing_chunks.append(index)
    progress(stage="loading_model" if missing_chunks else "assembling_cached", completed_chunks=cached_prefix, playable_chunks=cached_prefix, total_chunks=len(chunks), percent=1.0 if missing_chunks else 95.0, resumed_chunks=cached_prefix)

    model = None; ref_tokens = None; model_load_seconds = 0.0; prompt_encode_seconds = 0.0
    if missing_chunks:
        from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt
        from mlx_audio.tts.utils import load_model
        load_started = time.perf_counter()
        model = load_model(MODEL_ID, revision=MODEL_REVISION)
        model_load_seconds = time.perf_counter() - load_started
        progress(stage="encoding_voice", completed_chunks=cached_prefix, playable_chunks=cached_prefix, total_chunks=len(chunks), percent=5.0, model_load_seconds=round(model_load_seconds, 2), resumed_chunks=cached_prefix)
        prompt_started = time.perf_counter()
        ref_tokens = create_voice_clone_prompt(str(reference_audio), tokenizer=model.audio_tokenizer, ref_text=reference_text)
        prompt_encode_seconds = time.perf_counter() - prompt_started
        if getattr(ref_tokens, "size", 0) == 0: raise RuntimeError("empty clone-reference tokens")

    output_wav.parent.mkdir(parents=True, exist_ok=True); output_wav.unlink(missing_ok=True)
    chunk_reports: list[dict] = []; sample_rate: int | None = None; writer: sf.SoundFile | None = None; pending_tail: np.ndarray | None = None
    generation_started = time.perf_counter(); generated_new_count = 0; generated_new_seconds = 0.0; thermal_idle_seconds = 0.0
    try:
        for index, chunk in enumerate(chunks):
            checkpoint = checkpoint_dir / f"chunk_{index:05d}.flac" if checkpoint_dir is not None else None
            cached = bool(checkpoint is not None and checkpoint.is_file() and checkpoint.stat().st_size >= 256)
            if cached:
                audio, current_rate = sf.read(checkpoint, dtype="float32", always_2d=False); audio = _to_numpy(audio); current_rate = int(current_rate); elapsed = 0.0
            else:
                if model is None or ref_tokens is None: raise RuntimeError("voice model was not loaded for a missing chunk")
                started = time.perf_counter()
                results = list(model.generate(text=chunk.text, language=chunk.language, ref_tokens=ref_tokens, ref_text=reference_text, num_steps=num_steps, guidance_scale=guidance_scale))
                elapsed = time.perf_counter() - started
                if not results: raise RuntimeError(f"no audio returned for chunk {index}")
                result = results[-1]; audio = _to_numpy(result.audio); current_rate = int(getattr(result, "sample_rate", 0) or getattr(model, "sample_rate", 0))
                if checkpoint is not None: _write_checkpoint(checkpoint, audio, current_rate)
                generated_new_count += 1; generated_new_seconds += elapsed
            if current_rate <= 0 or not len(audio) or not np.isfinite(audio).all(): raise RuntimeError(f"invalid audio for chunk {index}")
            if sample_rate is None:
                sample_rate = current_rate; writer = sf.SoundFile(output_wav, mode="w", samplerate=sample_rate, channels=1, subtype="PCM_16", format="WAV")
            elif sample_rate != current_rate: raise RuntimeError("sample rate changed between chunks")
            assert writer is not None
            fade_samples = max(0, int(sample_rate * crossfade_ms / 1000)); pending_tail = _write_stream_part(writer, pending_tail, audio, fade_samples)
            seconds = len(audio) / current_rate
            chunk_reports.append({"index": index, "language": chunk.language, "chars": len(chunk.text), "generation_seconds": round(elapsed, 3), "audio_seconds": round(seconds, 3), "rtf": round(elapsed / seconds, 4) if elapsed else 0.0, "cached": cached})
            completed = index + 1; remaining_missing = sum(1 for item in missing_chunks if item > index); average_new = generated_new_seconds / generated_new_count if generated_new_count else 0.0
            remaining = max(0.0, (average_new + pause_seconds) * remaining_missing); percent = 5.0 + 90.0 * completed / len(chunks)
            progress(stage="synthesizing" if remaining_missing or not cached else "assembling_cached", completed_chunks=completed, playable_chunks=completed, total_chunks=len(chunks), percent=round(percent, 1), estimated_remaining_seconds=round(remaining, 1) if generated_new_count else None, generated_audio_seconds=round(sum(item["audio_seconds"] for item in chunk_reports), 1), resumed_chunks=sum(1 for item in chunk_reports if item["cached"]), thermal_idle_seconds=round(thermal_idle_seconds, 1))
            if not cached and pause_seconds > 0 and remaining_missing > 0:
                progress(stage="cooling", completed_chunks=completed, playable_chunks=completed, total_chunks=len(chunks), percent=round(percent, 1), estimated_remaining_seconds=round(remaining, 1), generated_audio_seconds=round(sum(item["audio_seconds"] for item in chunk_reports), 1), resumed_chunks=sum(1 for item in chunk_reports if item["cached"]), cooling_seconds=pause_seconds, thermal_idle_seconds=round(thermal_idle_seconds, 1))
                time.sleep(pause_seconds); thermal_idle_seconds += pause_seconds
        assert writer is not None and sample_rate is not None
        if pending_tail is not None and len(pending_tail): writer.write(pending_tail)
        total_frames = writer.tell()
    finally:
        if writer is not None: writer.close()

    generation_seconds = time.perf_counter() - generation_started
    progress(stage="exporting", completed_chunks=len(chunks), playable_chunks=len(chunks), total_chunks=len(chunks), percent=97.0, estimated_remaining_seconds=3.0, thermal_idle_seconds=round(thermal_idle_seconds, 1))
    if output_mp3 is not None:
        output_mp3.parent.mkdir(parents=True, exist_ok=True); _write_mp3(output_wav, output_mp3)
    audio_seconds = total_frames / sample_rate
    report = {
        "status": "GENERATED",
        "quality_status": "UNREVIEWED",
        "engine": "OmniVoice-MLX",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "engine_cache_version": ENGINE_CACHE_VERSION,
        "mlx_audio_version": _mlx_audio_version(),
        "num_steps": num_steps,
        "guidance_scale": guidance_scale,
        "crossfade_ms": crossfade_ms,
        "generation_mode": generation_mode,
        "thermal_pause_seconds": pause_seconds,
        "thermal_idle_seconds": round(thermal_idle_seconds, 3),
        "chunks": len(chunks),
        "resumed_chunks": sum(1 for item in chunk_reports if item["cached"]),
        "model_load_seconds": round(model_load_seconds, 3),
        "prompt_encode_seconds_one_time": round(prompt_encode_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "audio_seconds": round(audio_seconds, 3),
        "aggregate_rtf": round(generation_seconds / audio_seconds, 4),
        "chunk_reports": chunk_reports,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True); report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(stage="ready", completed_chunks=len(chunks), playable_chunks=len(chunks), total_chunks=len(chunks), percent=100.0, estimated_remaining_seconds=0.0, audio_seconds=round(audio_seconds, 1), thermal_idle_seconds=round(thermal_idle_seconds, 1))
    return report

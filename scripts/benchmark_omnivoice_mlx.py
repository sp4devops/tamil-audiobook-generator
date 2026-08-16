#!/usr/bin/env python3
"""Sustained Apple-Silicon benchmark for OmniVoice through MLX-Audio.

This script deliberately uses only non-private text and a caller-provided synthetic
reference. Private Stage-1 voice material belongs to the later human quality gate.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_ID = "mlx-community/OmniVoice-bf16"
HARD_RTF = 2.0
HARD_RSS_GIB = 3.0
TARGET_SECONDS = 60.0
MIN_AUDIO_SECONDS = 50.0

SEGMENTS = [
    ("tamil", "இது ஒரு நீண்ட தமிழ் ஆடியோ புத்தகத்திற்கான வேக சோதனை பகுதி."),
    ("english", "This is a sustained local audiobook generation speed benchmark."),
    ("tamil", "ஒவ்வொரு பகுதியும் ஒரே குரல் அடையாளத்தை தொடர்ந்து பயன்படுத்த வேண்டும்."),
    ("english", "Each segment should preserve one consistent cloned speaker identity."),
    ("tamil", "தமிழ் சொற்களின் இயல்பான ஓட்டமும் தெளிவான உச்சரிப்பும் முக்கியம்."),
    ("english", "Natural pacing matters, but this first gate measures runtime feasibility."),
    ("tamil", "நீண்ட நேரம் உருவாக்கும் போது நினைவக பயன்பாடு கட்டுப்பாட்டில் இருக்க வேண்டும்."),
    ("english", "Memory use must stay controlled during sequential long-form synthesis."),
    ("tamil", "இந்த சோதனை மேக் ஆப்பிள் சிலிக்கான் கணினியில் தொடர்ந்து இயங்குகிறது."),
    ("english", "The benchmark runs sequentially to resemble practical audiobook chunking."),
    ("tamil", "ஒரு நிமிட ஆடியோ இரண்டு நிமிடத்திற்குள் உருவாக வேண்டும் என்பது இலக்கு."),
    ("english", "The hard target is one minute of finished audio within two minutes."),
]


def _to_numpy(audio) -> np.ndarray:
    if hasattr(audio, "__array__"):
        arr = np.asarray(audio)
    else:
        arr = np.array(audio)
    return np.asarray(arr, dtype=np.float32).reshape(-1)


def _mlx_peak_bytes() -> int | None:
    try:
        import mlx.core as mx

        return int(mx.get_peak_memory())
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--segment-seconds", type=float, default=5.0)
    parser.add_argument("--num-steps", type=int, default=20)
    args = parser.parse_args()

    if not args.reference.is_file():
        raise SystemExit("Synthetic benchmark reference is missing")
    if not args.reference_text.strip():
        raise SystemExit("Synthetic benchmark reference text is empty")
    if args.segment_seconds <= 0:
        raise SystemExit("segment-seconds must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    from mlx_audio.tts.utils import load_model

    load_started = time.perf_counter()
    model = load_model(MODEL_ID)
    model_load_seconds = time.perf_counter() - load_started

    segment_reports: list[dict[str, object]] = []
    total_audio_seconds = 0.0
    generation_started = time.perf_counter()

    for index, (language, text) in enumerate(SEGMENTS):
        started = time.perf_counter()
        results = list(
            model.generate(
                text=text,
                language=language,
                ref_audio=str(args.reference),
                ref_text=args.reference_text,
                duration_s=args.segment_seconds,
                num_steps=args.num_steps,
            )
        )
        elapsed = time.perf_counter() - started
        if not results:
            raise RuntimeError(f"OmniVoice returned no audio for segment {index}")

        result = results[-1]
        audio = _to_numpy(result.audio)
        sample_rate = int(getattr(result, "sample_rate", 0) or getattr(model, "sample_rate", 0))
        if sample_rate <= 0:
            raise RuntimeError("Could not determine generated sample rate")
        if audio.size == 0:
            raise RuntimeError(f"OmniVoice returned empty audio for segment {index}")

        audio_seconds = audio.size / sample_rate
        total_audio_seconds += audio_seconds
        if index in (0, len(SEGMENTS) - 1):
            sf.write(args.output_dir / f"synthetic_segment_{index:02d}.wav", audio, sample_rate)

        segment_reports.append(
            {
                "index": index,
                "language": language,
                "generation_seconds": round(elapsed, 3),
                "audio_seconds": round(audio_seconds, 3),
                "rtf": round(elapsed / audio_seconds, 4),
                "sample_rate": sample_rate,
            }
        )

    generation_seconds = time.perf_counter() - generation_started
    aggregate_rtf = generation_seconds / total_audio_seconds
    mlx_peak_bytes = _mlx_peak_bytes()

    report = {
        "candidate": "OmniVoice-MLX",
        "model_id": MODEL_ID,
        "num_steps": args.num_steps,
        "benchmark_scope": "SYNTHETIC_REFERENCE_ZERO_SHOT_CLONING_TAMIL_ENGLISH_SEQUENTIAL",
        "private_voice_used": False,
        "model_load_seconds": round(model_load_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "audio_seconds": round(total_audio_seconds, 3),
        "aggregate_rtf": round(aggregate_rtf, 4),
        "rtf_limit": HARD_RTF,
        "rss_limit_gib": HARD_RSS_GIB,
        "minimum_audio_seconds": MIN_AUDIO_SECONDS,
        "requested_audio_seconds": TARGET_SECONDS,
        "mlx_peak_bytes": mlx_peak_bytes,
        "mlx_peak_gib": round(mlx_peak_bytes / (1024**3), 3) if mlx_peak_bytes else None,
        "speed_gate_pass": bool(total_audio_seconds >= MIN_AUDIO_SECONDS and aggregate_rtf <= HARD_RTF),
        "segments": segment_reports,
    }
    (args.output_dir / "omnivoice_runtime.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        "stage2_runtime="
        + json.dumps(
            {
                "num_steps": report["num_steps"],
                "audio_seconds": report["audio_seconds"],
                "generation_seconds": report["generation_seconds"],
                "aggregate_rtf": report["aggregate_rtf"],
                "speed_gate_pass": report["speed_gate_pass"],
                "mlx_peak_gib": report["mlx_peak_gib"],
            },
            separators=(",", ":"),
        )
    )
    if not report["speed_gate_pass"]:
        raise SystemExit(
            f"Stage 2 speed gate failed: {total_audio_seconds:.2f}s audio in "
            f"{generation_seconds:.2f}s (RTF={aggregate_rtf:.3f}, limit={HARD_RTF})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

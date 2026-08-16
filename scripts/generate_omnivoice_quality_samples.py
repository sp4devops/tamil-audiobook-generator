#!/usr/bin/env python3
"""Generate Stage-2 OmniVoice human-listening samples from a protected reference.

The reference transcript is read only to condition the model and is never printed or
written to the output directory. Human listening remains the authoritative identity gate.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_ID = "mlx-community/OmniVoice-bf16"
NUM_STEPS = 20
SAMPLE_SECONDS = 8.0

TARGETS = (
    (
        "tamil",
        "tamil",
        "இன்று நாம் ஒரு நீண்ட தமிழ் ஆடியோ புத்தகத்தை இயல்பான குரலில் கேட்கப் போகிறோம். கதையின் ஓட்டம் தெளிவாகவும் அமைதியாகவும் இருக்க வேண்டும்.",
    ),
    (
        "english",
        "english",
        "Today we are testing whether the same cloned speaker can narrate an English audiobook naturally, clearly, and consistently.",
    ),
    (
        "mixed",
        "None",
        "இன்று நம்முடைய audiobook generation test ஆரம்பிக்கிறது. The same voice should continue naturally, without changing the speaker identity. அடுத்த sentence-லும் அதே குரல் தொடர வேண்டும்.",
    ),
)


def _to_numpy(audio) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def _validate_audio(audio: np.ndarray, sample_rate: int, name: str) -> float:
    if sample_rate <= 0:
        raise RuntimeError(f"Invalid sample rate for {name}")
    if audio.size == 0 or not np.isfinite(audio).all():
        raise RuntimeError(f"Invalid waveform for {name}")
    duration = audio.size / sample_rate
    if not 2.0 <= duration <= 15.0:
        raise RuntimeError(f"Unexpected duration for {name}: {duration:.3f}s")
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-4:
        raise RuntimeError(f"Near-silent waveform for {name}")
    return duration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if not args.reference.is_file():
        raise SystemExit("Protected reference audio is missing")
    if not args.reference_text_file.is_file():
        raise SystemExit("Protected reference transcript is missing")
    ref_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    if not ref_text:
        raise SystemExit("Protected reference transcript is empty")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt
    from mlx_audio.tts.utils import load_model

    load_started = time.perf_counter()
    model = load_model(MODEL_ID)
    model_load_seconds = time.perf_counter() - load_started

    prompt_started = time.perf_counter()
    ref_tokens = create_voice_clone_prompt(
        str(args.reference), tokenizer=model.audio_tokenizer, ref_text=ref_text
    )
    prompt_encode_seconds = time.perf_counter() - prompt_started
    if getattr(ref_tokens, "size", 0) == 0:
        raise RuntimeError("Empty reusable clone-reference tokens")

    samples = []
    generation_started = time.perf_counter()
    for name, language, text in TARGETS:
        started = time.perf_counter()
        results = list(
            model.generate(
                text=text,
                language=language,
                ref_tokens=ref_tokens,
                ref_text=ref_text,
                duration_s=SAMPLE_SECONDS,
                num_steps=NUM_STEPS,
            )
        )
        elapsed = time.perf_counter() - started
        if not results:
            raise RuntimeError(f"No audio returned for {name}")
        result = results[-1]
        audio = _to_numpy(result.audio)
        sample_rate = int(
            getattr(result, "sample_rate", 0) or getattr(model, "sample_rate", 0)
        )
        duration = _validate_audio(audio, sample_rate, name)
        sf.write(args.output_dir / f"{name}_listening_sample.wav", audio, sample_rate)
        samples.append(
            {
                "name": name,
                "language_mode": language,
                "generation_seconds": round(elapsed, 3),
                "audio_seconds": round(duration, 3),
                "rtf": round(elapsed / duration, 4),
                "sample_rate": sample_rate,
                "waveform_valid": True,
            }
        )

    generation_seconds = time.perf_counter() - generation_started
    total_audio = sum(float(item["audio_seconds"]) for item in samples)
    report = {
        "status": "READY_FOR_HUMAN_LISTENING",
        "candidate": "OmniVoice-MLX",
        "model_id": MODEL_ID,
        "num_steps": NUM_STEPS,
        "reference_conditioning": "ENCODE_ONCE_REUSE_REF_TOKENS",
        "protected_reference_used": True,
        "reference_text_exposed": False,
        "model_load_seconds": round(model_load_seconds, 3),
        "prompt_encode_seconds_one_time": round(prompt_encode_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "audio_seconds": round(total_audio, 3),
        "aggregate_rtf": round(generation_seconds / total_audio, 4),
        "human_identity_acceptance": "PENDING",
        "samples": samples,
    }
    (args.output_dir / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "quality_samples=READY_FOR_HUMAN_LISTENING "
        f"audio_seconds={report['audio_seconds']} aggregate_rtf={report['aggregate_rtf']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

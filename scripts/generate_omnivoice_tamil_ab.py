#!/usr/bin/env python3
"""Generate a Tamil-only OmniVoice A/B candidate at a configurable step count.

The accepted Stage-1 reference is caller-provided and remains transient. This script
writes only the new listening sample plus safe timing metadata.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_ID = "mlx-community/OmniVoice-bf16"
TARGET_TEXT = "இன்று நாம் ஒரு நீண்ட தமிழ் ஆடியோ புத்தகத்தை இயல்பான குரலில் கேட்கப் போகிறோம். கதையின் ஓட்டம் தெளிவாகவும் அமைதியாகவும் இருக்க வேண்டும்."
SAMPLE_SECONDS = 8.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--num-steps", type=int, default=18)
    args = parser.parse_args()

    if not args.reference.is_file() or not args.reference_text_file.is_file():
        raise SystemExit("Transient Stage-1 reference pair is missing")
    ref_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    if not ref_text:
        raise SystemExit("Transient reference transcript is empty")
    if args.num_steps < 8 or args.num_steps > 32:
        raise SystemExit("num-steps must be between 8 and 32")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt
    from mlx_audio.tts.utils import load_model

    model = load_model(MODEL_ID)
    ref_tokens = create_voice_clone_prompt(
        str(args.reference), tokenizer=model.audio_tokenizer, ref_text=ref_text
    )
    if getattr(ref_tokens, "size", 0) == 0:
        raise RuntimeError("Empty clone prompt")

    started = time.perf_counter()
    results = list(
        model.generate(
            text=TARGET_TEXT,
            language="tamil",
            ref_tokens=ref_tokens,
            ref_text=ref_text,
            duration_s=SAMPLE_SECONDS,
            num_steps=args.num_steps,
        )
    )
    elapsed = time.perf_counter() - started
    if not results:
        raise RuntimeError("No Tamil audio returned")

    result = results[-1]
    audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
    sample_rate = int(getattr(result, "sample_rate", 0) or getattr(model, "sample_rate", 0))
    if sample_rate <= 0 or audio.size == 0 or not np.isfinite(audio).all():
        raise RuntimeError("Invalid Tamil waveform")
    duration = audio.size / sample_rate
    if not 2.0 <= duration <= 15.0:
        raise RuntimeError(f"Unexpected Tamil duration: {duration:.3f}s")
    if float(np.max(np.abs(audio))) < 1e-4:
        raise RuntimeError("Near-silent Tamil waveform")

    output_name = f"tamil_{args.num_steps}step_listening_sample.wav"
    sf.write(args.output_dir / output_name, audio, sample_rate)
    rtf = elapsed / duration
    report = {
        "status": "READY_FOR_HUMAN_AB_LISTENING",
        "candidate": "OmniVoice-MLX",
        "model_id": MODEL_ID,
        "num_steps": args.num_steps,
        "reference_conditioning": "ENCODE_ONCE_REUSE_REF_TOKENS",
        "audio_seconds": round(duration, 3),
        "generation_seconds": round(elapsed, 3),
        "rtf": round(rtf, 4),
        "speed_gate_pass": bool(rtf <= 2.0),
        "human_quality_acceptance": "PENDING",
        "output": output_name,
    }
    (args.output_dir / "tamil_ab_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"tamil_ab steps={args.num_steps} audio_seconds={duration:.3f} "
        f"generation_seconds={elapsed:.3f} rtf={rtf:.4f} "
        f"speed_gate_pass={str(rtf <= 2.0).lower()}"
    )
    if rtf > 2.0:
        raise SystemExit(f"Tamil A/B speed gate failed at {args.num_steps} steps: RTF={rtf:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

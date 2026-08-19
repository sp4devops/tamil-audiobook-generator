#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow direct execution as `python scripts/generate_audiobook.py` from a clean
# checkout without requiring the project to be installed as a wheel first.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tamil_audiobook.controlled_engine import synthesize_audiobook_with_controls
from tamil_audiobook.engine import DEFAULT_GUIDANCE_SCALE
from tamil_audiobook.generation_controls import (
    DEFAULT_CLASS_TEMPERATURE,
    DEFAULT_LAYER_PENALTY_FACTOR,
    DEFAULT_POSITION_TEMPERATURE,
    DEFAULT_T_SHIFT,
    OmniVoiceGenerationControls,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local Tamil/English audiobook with OmniVoice MLX")
    parser.add_argument("--text-file", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text-file", type=Path, required=True)
    parser.add_argument("--output-wav", type=Path, required=True)
    parser.add_argument("--output-mp3", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--checkpoint-dir", type=Path, help="Persist generated chunks here so interrupted long books can resume")
    parser.add_argument("--num-steps", type=int, default=20)
    parser.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE)

    quality = parser.add_argument_group("OmniVoice quality controls")
    quality.add_argument(
        "--narration-style",
        choices=("auto", "neutral", "audiobook"),
        default="auto",
        help="auto keeps semantic P3 prosody, neutral disables instructions, audiobook also styles neutral narration",
    )
    quality.add_argument(
        "--duration-scale",
        type=float,
        help="Opt-in native duration multiplier: <1.0 shorter/faster, >1.0 longer/slower; allowed 0.75..1.35",
    )
    quality.add_argument("--class-temperature", type=float, default=DEFAULT_CLASS_TEMPERATURE)
    quality.add_argument("--position-temperature", type=float, default=DEFAULT_POSITION_TEMPERATURE)
    quality.add_argument("--layer-penalty-factor", type=float, default=DEFAULT_LAYER_PENALTY_FACTOR)
    quality.add_argument("--t-shift", type=float, default=DEFAULT_T_SHIFT)
    args = parser.parse_args()

    controls = OmniVoiceGenerationControls(
        narration_style=args.narration_style,
        duration_scale=args.duration_scale,
        class_temperature=args.class_temperature,
        position_temperature=args.position_temperature,
        layer_penalty_factor=args.layer_penalty_factor,
        t_shift=args.t_shift,
    ).validated()

    text = args.text_file.read_text(encoding="utf-8")
    reference_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    report = synthesize_audiobook_with_controls(
        controls=controls,
        text=text,
        reference_audio=args.reference,
        reference_text=reference_text,
        output_wav=args.output_wav,
        output_mp3=args.output_mp3,
        num_steps=args.num_steps,
        guidance_scale=args.guidance_scale,
        report_path=args.report,
        checkpoint_dir=args.checkpoint_dir,
    )
    print(json.dumps({
        "status": report["status"],
        "audio_seconds": report["audio_seconds"],
        "generation_seconds": report["generation_seconds"],
        "aggregate_rtf": report["aggregate_rtf"],
        "guidance_scale": report["guidance_scale"],
        "chunks": report["chunks"],
        "resumed_chunks": report.get("resumed_chunks", 0),
        "omnivoice_controls": report.get("omnivoice_controls", {}),
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

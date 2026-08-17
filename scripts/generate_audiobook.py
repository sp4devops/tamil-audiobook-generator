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

from tamil_audiobook.engine import DEFAULT_GUIDANCE_SCALE, synthesize_audiobook


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
    args = parser.parse_args()

    text = args.text_file.read_text(encoding="utf-8")
    reference_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    report = synthesize_audiobook(
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
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

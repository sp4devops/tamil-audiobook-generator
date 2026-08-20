#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tamil_audiobook.controlled_engine import synthesize_audiobook_with_controls
from tamil_audiobook.engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS
from tamil_audiobook.generation_controls import OmniVoiceGenerationControls

BENCHMARK_PATH = REPO_ROOT / "benchmarks" / "tamil_voice_quality.json"


def load_cases() -> list[dict]:
    data = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    return list(data["cases"])


def _quality_alarms(report: dict) -> list[str]:
    alarms: list[str] = []
    chunks = list(report.get("chunk_reports", []))
    if not chunks:
        alarms.append("no_chunks")
        return alarms
    if float(report.get("audio_seconds", 0.0)) <= 0:
        alarms.append("empty_audio")
    if float(report.get("max_continuity_gain_db", 0.0)) >= 1.25:
        alarms.append("continuity_gain_hit_limit")
    for chunk in chunks:
        if float(chunk.get("audio_seconds", 0.0)) < 0.25:
            alarms.append(f"chunk_{chunk.get('index')}_too_short")
        peak = float(chunk.get("continuity_peak_after", 0.0))
        if peak >= 0.98:
            alarms.append(f"chunk_{chunk.get('index')}_peak_at_limit")
    return alarms


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the permanent Tamil cloned-voice quality benchmark")
    parser.add_argument("--list", action="store_true", help="List benchmark case IDs and exit")
    parser.add_argument("--case", action="append", dest="cases", help="Benchmark case ID; repeat to select multiple cases")
    parser.add_argument("--category", action="append", dest="categories", help="Select every case in a category")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-text-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-output"))
    parser.add_argument("--narration-style", choices=("auto", "neutral", "audiobook"), default="auto")
    parser.add_argument("--duration-scale", type=float)
    parser.add_argument("--class-temperature", type=float, default=0.0)
    parser.add_argument("--position-temperature", type=float, default=5.0)
    parser.add_argument("--layer-penalty-factor", type=float, default=5.0)
    parser.add_argument("--t-shift", type=float, default=0.1)
    args = parser.parse_args()

    all_cases = load_cases()
    if args.list:
        for case in all_cases:
            print(f"{case['id']:18} {case['category']:24} {case['text']}")
        return 0

    if args.reference is None or args.reference_text_file is None:
        parser.error("--reference and --reference-text-file are required when generating benchmark audio")

    requested_ids = set(args.cases or [])
    requested_categories = set(args.categories or [])
    if not requested_ids and not requested_categories:
        parser.error("select at least one --case or --category; use --list to inspect the corpus")

    known_ids = {case["id"] for case in all_cases}
    unknown = requested_ids - known_ids
    if unknown:
        parser.error(f"unknown benchmark case(s): {', '.join(sorted(unknown))}")

    selected = [
        case for case in all_cases
        if case["id"] in requested_ids or case["category"] in requested_categories
    ]
    if not selected:
        parser.error("no benchmark cases matched the requested categories")

    controls = OmniVoiceGenerationControls(
        narration_style=args.narration_style,
        duration_scale=args.duration_scale,
        class_temperature=args.class_temperature,
        position_temperature=args.position_temperature,
        layer_penalty_factor=args.layer_penalty_factor,
        t_shift=args.t_shift,
    ).validated()
    reference_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "benchmark": "tamil-voice-quality",
        "controls": controls.as_dict(),
        "human_gate": True,
        "automated_gate_scope": "audio-health-and-routing-regression-only",
        "cases": [],
    }
    for case in selected:
        case_dir = args.output_dir / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        report = synthesize_audiobook_with_controls(
            controls=controls,
            text=case["text"],
            reference_audio=args.reference,
            reference_text=reference_text,
            output_wav=case_dir / "sample.wav",
            output_mp3=case_dir / "sample.mp3",
            num_steps=DEFAULT_NUM_STEPS,
            guidance_scale=DEFAULT_GUIDANCE_SCALE,
            report_path=case_dir / "report.json",
            checkpoint_dir=case_dir / "chunks",
        )
        alarms = _quality_alarms(report)
        manifest["cases"].append({
            "id": case["id"],
            "category": case["category"],
            "listen_for": case["listen_for"],
            "audio_seconds": report["audio_seconds"],
            "aggregate_rtf": report["aggregate_rtf"],
            "contextual_indian_english_chunks": report.get("contextual_indian_english_chunks", 0),
            "quality_alarms": alarms,
            "quality_status": "UNREVIEWED",
        })
        print(f"{case['id']}: {case_dir / 'sample.mp3'}")

    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

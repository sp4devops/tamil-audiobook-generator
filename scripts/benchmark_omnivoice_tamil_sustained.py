#!/usr/bin/env python3
"""Sustained Tamil audiobook benchmark for OmniVoice MLX.

Uses one accepted Stage-1 voice reference, encodes it once, then reuses the clone
prompt across 12 sequential Tamil chunks. This measures the production-relevant
one-minute audiobook path rather than short-clip fixed overhead.
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
SEGMENT_SECONDS = 5.0
HARD_RTF = 2.0
MIN_AUDIO_SECONDS = 59.0

TAMIL_SEGMENTS = [
    "இன்று நாம் ஒரு நீண்ட தமிழ் ஆடியோ புத்தகத்தை இயல்பான குரலில் கேட்கப் போகிறோம்.",
    "கதையின் ஒவ்வொரு பகுதியும் தெளிவாகவும் அமைதியான ஓட்டத்துடனும் தொடர வேண்டும்.",
    "ஒரே பேச்சாளரின் குரல் அடையாளம் தொடக்கம் முதல் முடிவு வரை மாறாமல் இருக்க வேண்டும்.",
    "தமிழ் சொற்களின் உச்சரிப்பும் இடைவெளிகளும் கேட்பவருக்கு இயல்பாக உணரப்பட வேண்டும்.",
    "நீண்ட உரையை சிறிய பகுதிகளாக உருவாக்கினாலும் குரலின் தன்மை தொடர்ந்து ஒரே மாதிரியாக இருக்க வேண்டும்.",
    "ஆடியோ புத்தகத்தில் வேகம் மட்டும் அல்லாமல் உணர்ச்சி மற்றும் சரியான சொல் ஓட்டமும் முக்கியம்.",
    "ஒவ்வொரு வாக்கியமும் அடுத்த வாக்கியத்துடன் இணையும் போது திடீர் குரல் மாற்றம் இருக்கக் கூடாது.",
    "கேட்பவருக்கு நீண்ட நேரம் சோர்வு வராமல் மென்மையான மற்றும் நிலையான வாசிப்பு தேவைப்படுகிறது.",
    "இந்த சோதனையில் ஒரே குறிப்பு குரலை மீண்டும் குறியாக்காமல் அனைத்து பகுதிகளுக்கும் பயன்படுத்துகிறோம்.",
    "அதனால் ஆடியோ புத்தகத்தின் முழு செயல்திறனை நிஜமான தொடர்ச்சியான சூழலில் அளக்க முடிகிறது.",
    "ஒரு நிமிட முடிக்கப்பட்ட ஆடியோ இரண்டு நிமிடங்களுக்குள் உருவாக வேண்டும் என்பது நமது கடின இலக்கு.",
    "குரல் தரத்தை குறைக்காமல் இந்த வேகத்தை அடைந்தால்தான் இந்த கட்டமைப்பு ஏற்றுக்கொள்ளப்படும்.",
]


def _to_numpy(audio) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-text-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if not args.reference.is_file():
        raise SystemExit("Accepted Stage-1 reference audio is missing")
    if not args.reference_text_file.is_file():
        raise SystemExit("Accepted Stage-1 reference text is missing")
    ref_text = args.reference_text_file.read_text(encoding="utf-8").strip()
    if not ref_text:
        raise SystemExit("Accepted Stage-1 reference text is empty")

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

    reports: list[dict[str, object]] = []
    total_audio_seconds = 0.0
    generation_started = time.perf_counter()

    for index, text in enumerate(TAMIL_SEGMENTS):
        started = time.perf_counter()
        results = list(
            model.generate(
                text=text,
                language="tamil",
                ref_tokens=ref_tokens,
                ref_text=ref_text,
                duration_s=SEGMENT_SECONDS,
                num_steps=NUM_STEPS,
            )
        )
        elapsed = time.perf_counter() - started
        if not results:
            raise RuntimeError(f"No audio returned for Tamil segment {index}")

        result = results[-1]
        audio = _to_numpy(result.audio)
        sample_rate = int(
            getattr(result, "sample_rate", 0) or getattr(model, "sample_rate", 0)
        )
        if sample_rate <= 0 or audio.size == 0 or not np.isfinite(audio).all():
            raise RuntimeError(f"Invalid Tamil waveform for segment {index}")

        audio_seconds = audio.size / sample_rate
        total_audio_seconds += audio_seconds
        if index in (0, len(TAMIL_SEGMENTS) - 1):
            sf.write(args.output_dir / f"tamil_segment_{index:02d}.wav", audio, sample_rate)

        reports.append(
            {
                "index": index,
                "generation_seconds": round(elapsed, 3),
                "audio_seconds": round(audio_seconds, 3),
                "rtf": round(elapsed / audio_seconds, 4),
                "sample_rate": sample_rate,
            }
        )

    generation_seconds = time.perf_counter() - generation_started
    aggregate_rtf = generation_seconds / total_audio_seconds
    speed_gate_pass = bool(total_audio_seconds >= MIN_AUDIO_SECONDS and aggregate_rtf <= HARD_RTF)

    report = {
        "status": "PASS" if speed_gate_pass else "FAIL",
        "candidate": "OmniVoice-MLX",
        "model_id": MODEL_ID,
        "language": "tamil",
        "num_steps": NUM_STEPS,
        "reference_conditioning": "ENCODE_ONCE_REUSE_REF_TOKENS",
        "accepted_stage1_voice_used": True,
        "model_load_seconds": round(model_load_seconds, 3),
        "prompt_encode_seconds_one_time": round(prompt_encode_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "audio_seconds": round(total_audio_seconds, 3),
        "aggregate_rtf": round(aggregate_rtf, 4),
        "hard_rtf_limit": HARD_RTF,
        "speed_gate_pass": speed_gate_pass,
        "segments": reports,
    }
    (args.output_dir / "tamil_sustained_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "tamil_sustained "
        f"audio_seconds={report['audio_seconds']} "
        f"generation_seconds={report['generation_seconds']} "
        f"aggregate_rtf={report['aggregate_rtf']} "
        f"speed_gate_pass={str(speed_gate_pass).lower()}"
    )
    if not speed_gate_pass:
        raise SystemExit(
            f"Sustained Tamil speed gate failed: {total_audio_seconds:.2f}s audio in "
            f"{generation_seconds:.2f}s (RTF={aggregate_rtf:.3f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

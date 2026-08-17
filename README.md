# tamil-audiobook-generator

Stage 2 of the local Tamil voice-cloning project.

## Goal

Build a lightweight audiobook engine for Apple Silicon that preserves the accepted speaker identity while making long-form Tamil + English/Tanglish generation practical.

### Hard acceptance targets

- Apple M2 Mac with 8 GB unified memory.
- Local-only final runtime.
- Free/open-source components only; no paid APIs.
- Tamil, English, and mixed Tamil/English in one consistent speaker identity.
- Minimum sustained speed: **1 minute of finished audio in no more than 2 minutes** (`RTF <= 2.0`).
- Runtime memory ceiling: **3 GiB RSS**.
- The **human quality gate** is authoritative: no engine is accepted solely from automated metrics or speed.

## Accepted voice configuration

Human listening selected **identity candidate C** at approximately **95% speaker match** with natural flow preserved.

The accepted production configuration is now locked to:

- Engine/model: OmniVoice through MLX-Audio, `mlx-community/OmniVoice-bf16`.
- Reference: accepted Stage-1 mixed Tamil/English listening reference, recovered transiently and never shipped in artifacts.
- Synthesis steps: **20**.
- Classifier-free guidance scale: **2.5**.
- Crossfade: **55 ms**.
- Clone-reference tokens encoded once per audiobook session and reused across all chunks.

Rejected/older identity settings remain diagnostic only. In particular, 18 synthesis steps were rejected because human listening dropped substantially in Tamil quality.

## Production engine

The reusable engine lives in `tamil_audiobook/engine.py` with CLI entry point `scripts/generate_audiobook.py`.

Current production behavior:

- 20-step OmniVoice MLX synthesis with guidance 2.5.
- Clone-reference prompt encoded once per audiobook session.
- Sentence-aware long-text chunking.
- Tamil, English, and mixed-language mode selection per chunk.
- 55 ms crossfade stitching between generated chunks.
- WAV output and optional MP3 export through local FFmpeg.
- JSON runtime report with per-chunk and aggregate RTF.
- Unit-tested text chunking, language selection, duration bounds, and crossfade logic.
- Exact validated Apple-Silicon Python package versions pinned in `stage2_requirements.txt`.

## Apple Silicon acceptance results

On the standard GitHub `macos-14-arm64` runner with 7 GiB physical RAM:

- Earlier mixed 60-second benchmark at 20 steps: **RTF 1.3664**, max RSS **1.223 GiB**.
- Tamil-only sustained benchmark at 20 steps: **RTF 1.5299**, max RSS **1.171 GiB**, zero swaps.
- Production engine using the human-accepted C voice configuration: **96.6 s finished audio in 130.347 s synthesis**, **RTF 1.3494**, **max RSS 1.116 GiB**, zero swaps, WAV/MP3 PASS.
- This equals roughly **81 seconds of synthesis per finished minute**, comfortably inside the 120-second hard target.

Relevant successful runs:

- `stage2-omnivoice-tamil-sustained` run **31978886925**.
- Identity guidance sweep run **31980480116**, where candidate C was selected by human listening at approximately 95% speaker match.
- Exact accepted-C production regression run **31990035829**: PASS.

## Final sustained gate

The final technical gate is `stage2-audiobook-10min`, which runs the real production engine for roughly ten minutes of finished bilingual audiobook audio using the same human-accepted C configuration. It enforces:

- finished audio >= 540 seconds,
- aggregate RTF <= 2.0,
- RSS <= 3 GiB,
- 20 steps and guidance 2.5,
- successful MP3 export,
- cleanup of transient reference material.

Stage 2 should only be declared technically complete after this sustained gate passes. The user-approved ~95% speaker identity remains the human quality baseline.

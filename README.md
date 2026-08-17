# tamil-audiobook-generator

Stage 2 of the local Tamil voice-cloning project.

## Status: COMPLETE

Stage 2 is technically complete and the production voice configuration has passed the human quality gate.

Human listening selected **identity candidate C** at approximately **95% speaker match** with natural flow preserved. The same configuration then passed both the production regression and a sustained 11+ minute audiobook test on Apple Silicon.

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

## Accepted production voice configuration

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
- Unit-tested text chunking, language selection, duration bounds, crossfade logic, and locked accepted voice defaults.
- Exact validated Apple-Silicon Python package versions pinned in `stage2_requirements.txt`.
- One-command local Apple-Silicon setup in `scripts/setup_macos.sh`.

## Apple Silicon acceptance results

On the standard GitHub `macos-14-arm64` runner with 7 GiB physical RAM:

### Accepted-C production regression

Run **31990035829**:

- Finished audio: **96.6 s**.
- Generation time: **130.347 s**.
- Aggregate **RTF 1.3494**.
- Maximum RSS: **1.116 GiB**.
- Swaps: **0**.
- WAV export: PASS.
- MP3 export: PASS.
- Accepted voice configuration check: PASS.

### Final sustained audiobook gate

Run **31990064057**:

- Finished audio: **678.99 s** (~11 min 19 s).
- Generation time: **907.888 s**.
- Aggregate **RTF 1.3371**.
- Equivalent generation time: approximately **80.2 seconds per finished audio minute**.
- Chunks: **63**.
- Maximum RSS: **1.037 GiB**.
- Swaps: **0**.
- Synthesis steps: **20**.
- Guidance scale: **2.5**.
- MP3 export: PASS.
- Private reference cleanup: PASS.
- Final sustained acceptance: **PASS**.

The sustained result remains comfortably inside both hard limits: **RTF <= 2.0** and **RSS <= 3 GiB**.

## Relevant successful runs

- `stage2-omnivoice-tamil-sustained` run **31978886925**.
- Identity guidance sweep run **31980480116**, where candidate C was selected by human listening at approximately 95% speaker match.
- Accepted-C production regression run **31990035829**.
- Final sustained audiobook acceptance run **31990064057**.

## Completion statement

Stage 2 has met its defined acceptance criteria: human-approved speaker identity and naturalness, one consistent bilingual voice path, local/open-source operation, sustained audiobook throughput below the two-minutes-per-minute ceiling, and memory use well below 3 GiB RSS on Apple Silicon.

The engine is ready for local audiobook generation on the target Mac.

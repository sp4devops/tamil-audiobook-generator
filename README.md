# tamil-audiobook-generator

Stage 2 of the local Tamil voice-cloning project.

## Goal

Build a lightweight audiobook engine for Apple Silicon that preserves the accepted Stage-1 speaker identity while making long-form Tamil + English/Tanglish generation practical.

### Hard acceptance targets

- Apple M2 Mac with 8 GB unified memory.
- Local-only final runtime.
- Free/open-source components only; no paid APIs.
- Tamil, English, and mixed Tamil/English in one consistent speaker identity.
- Minimum sustained speed: **1 minute of finished audio in no more than 2 minutes** (`RTF <= 2.0`).
- Runtime memory ceiling for Stage 2 experiments: **3 GiB RSS** unless explicitly revised.
- Stage-1 voice is the quality baseline; Stage-2 speed work must not modify the completed Stage-1 repository.
- The **human quality gate** remains authoritative: no engine is accepted solely from automated metrics or speed.

## Candidate A: OmniVoice on MLX

OmniVoice through MLX-Audio is the current Stage-2 candidate because it combines Apple-Silicon-native MLX inference, zero-shot voice cloning, and multilingual synthesis including Tamil and English.

### Current measured status

- **20 synthesis steps is the retained quality floor.** Human listening rated the Tamil 20-step sample at approximately **90% voice match**.
- **18 steps is rejected.** Human listening rated the Tamil 18-step sample at approximately **70% voice match**, despite its better short-clip speed.
- The accepted Stage-1 voice reference is bridged transiently from its verified GitHub Actions artifact. The reference is deleted before Stage-2 artifacts are uploaded.
- Reusable OmniVoice clone-reference tokens are encoded once and reused across audiobook chunks.
- The production engine now chunks long Tamil/English text, detects Tamil/English/mixed chunks, synthesizes sequentially, stitches with a **55 ms crossfade**, and exports both WAV and MP3.

### Apple Silicon performance results

On the standard GitHub `macos-14-arm64` runner with 7 GiB physical RAM:

- Mixed Tamil/English synthetic 60-second benchmark at 20 steps: **60.0 s audio in 81.986 s**, aggregate **RTF 1.3664**, max RSS **1.223 GiB**.
- Tamil-only sustained benchmark with the accepted Stage-1 voice at 20 steps: **60.0 s audio in 91.795 s**, aggregate **RTF 1.5299**, max RSS **1.171 GiB**, zero swaps.
- Production audiobook-engine acceptance run using the accepted Stage-1 voice at 20 steps: **96.6 s finished audio in 120.496 s synthesis**, aggregate **RTF 1.2474**, max RSS **1.352 GiB**, WAV and MP3 export PASS, 9 stitched chunks.
- The production-engine result is equivalent to roughly **75 seconds of synthesis per finished minute**, comfortably inside the 120-second hard target.

Relevant successful runs:

- `stage2-omnivoice-tamil-sustained` run **31978886925** at commit `ab9579e8068f32459e9b3b0b82396caa4d0322bf`.
- `stage2-audiobook-engine` run **31979462445** at commit `a0cde427779c2e91ec378a0443da3033b5f8a7f9`.

## Production engine

The reusable engine lives in `tamil_audiobook/engine.py` with CLI entry point `scripts/generate_audiobook.py`.

Current production behavior:

- 20-step OmniVoice MLX synthesis.
- Clone-reference prompt encoded once per audiobook session.
- Sentence-aware long-text chunking.
- Tamil, English, and mixed-language mode selection per chunk.
- 55 ms crossfade stitching between generated chunks.
- WAV output and optional MP3 export through local FFmpeg.
- JSON runtime report with per-chunk and aggregate RTF.
- Unit-tested text chunking, language selection, duration bounds, and crossfade logic.

## Acceptance state

The **production performance, memory, WAV export, and MP3 export gates are PASS at the retained 20-step quality setting**.

Human quality validation is still authoritative. Tamil 20-step quality is approximately 90% by user listening. The generated 96.6-second bilingual audiobook sample from run `31979462445` must be listened to before declaring the full bilingual Stage-2 engine complete.

## Benchmark design

The sustained benchmarks use sequential audiobook-style chunks rather than one tiny sentence. They record:

- model-load wall time,
- one-time clone-reference encoding time,
- generation wall time per segment,
- actual generated duration per segment,
- aggregate real-time factor (RTF),
- macOS maximum resident set size (RSS),
- PASS/FAIL against the `RTF <= 2.0` and `RSS <= 3 GiB` requirements.

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

## Candidate A: OmniVoice on MLX

The first feasibility candidate is OmniVoice through MLX-Audio because it combines Apple-Silicon-native MLX inference, zero-shot voice cloning, and explicit multilingual support including Tamil and English.

Candidate A is accepted only after both gates pass:

1. **Performance gate:** approximately 60 seconds of sequential cloned-voice audiobook-style output must complete with aggregate `RTF <= 2.0` and process RSS `<= 3 GiB` on Apple Silicon.
2. **Human quality gate:** the candidate must be generated with the accepted Stage-1 speaker reference and listened to before speaker-match quality is claimed.

The initial CI benchmark intentionally uses a synthetic macOS system-voice reference created inside the job. This exercises the cloning path without committing or exposing private voice material.

## Benchmark design

The first benchmark generates 12 sequential segments (six Tamil, six English), targeting ~5 seconds each. This is deliberately closer to audiobook chunking than a single tiny sentence. It records:

- model-load wall time,
- generation wall time per segment,
- actual generated duration per segment,
- aggregate real-time factor (RTF),
- macOS maximum resident set size (RSS),
- MLX peak allocator memory when available,
- PASS/FAIL against the `RTF <= 2.0` and `RSS <= 3 GiB` requirements.

No voice-match claim is made from the synthetic-reference benchmark.

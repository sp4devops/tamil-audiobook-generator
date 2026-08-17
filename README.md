# tamil-audiobook-generator

Stage 2 of the local Tamil voice-cloning project.

## Status: ENGINE COMPLETE + LOCAL APP

The Stage-2 voice engine is technically complete and the production voice configuration has passed the human quality gate.

Human listening selected **identity candidate C** at approximately **95% speaker match** with natural flow preserved. The same configuration then passed both the production regression and a sustained 11+ minute audiobook test on Apple Silicon.

The repository now also contains **ListenLeaf**, a local-only CLI + browser UI for importing books, generating audio, reading while listening, organizing a library, and tuning playback.

## Goal

Build a lightweight audiobook engine and long-form listening app for Apple Silicon that preserves the accepted speaker identity while making Tamil + English/Tanglish books practical to generate and consume.

### Hard acceptance targets

- Apple M2 Mac with 8 GB unified memory.
- Local-only final runtime.
- Free/open-source components only; no paid APIs.
- Tamil, English, and mixed Tamil/English in one consistent speaker identity.
- Minimum sustained speed: **1 minute of finished audio in no more than 2 minutes** (`RTF <= 2.0`).
- Runtime memory ceiling: **3 GiB RSS**.
- The **human quality gate** is authoritative: no engine is accepted solely from automated metrics or speed.

## Quick start on Apple Silicon

```bash
git clone https://github.com/sp4devops/tamil-audiobook-generator.git
cd tamil-audiobook-generator
bash scripts/setup_macos.sh
source .venv/bin/activate
python scripts/audiobook.py serve
```

The UI listens on `127.0.0.1:8765` by default and opens in the local browser. Library data is stored under `~/.tamil_audiobook` unless `TAMIL_AUDIOBOOK_HOME` or `--library` is used.

### CLI examples

```bash
# Import a text or PDF book.
python scripts/audiobook.py import ~/Books/my-book.pdf --title "My Book" --author "Author"

# List the local library.
python scripts/audiobook.py list

# Configure the private local voice reference from a WAV + exact transcript.
python scripts/audiobook.py voice ~/voice/reference.wav ~/voice/reference.txt

# Generate a book by ID using the accepted C voice configuration.
python scripts/audiobook.py generate BOOK_ID

# Launch the browser UI without automatically opening a tab.
python scripts/audiobook.py serve --no-open
```

The older low-level `scripts/generate_audiobook.py` remains available for direct text-file-to-audio jobs.

## ListenLeaf local UI

The browser UI intentionally behaves like a modern media player while remaining entirely local.

### Library and import

- Import **PDF, TXT and Markdown**.
- Extract PDF text locally with `pypdf`.
- Persistent local book metadata, source text, audio, cue files and progress.
- Continue-listening shelf.
- Search-friendly library rows and book detail/player view.
- Create playlists and add books to them.
- Follow authors and series locally.
- Private local activity feed.

### Spotify-style read along

Every generated book gets a local `cues.json` sidecar derived from the exact chunks sent to the accepted TTS engine. Each cue records text plus its audio start/end time.

During playback the UI:

- highlights the active text chunk,
- automatically scrolls it into the reading focus area,
- seeks correctly when the audio scrubber moves,
- resumes from saved listening position,
- supports focus-line mode that dims surrounding text,
- supports adjustable reader text size.

This read-along system does not require cloud speech recognition or forced-alignment services.

### Playback and sound controls

- Play/pause, ±15 seconds, seek, volume and sleep timer.
- Playback speeds from 0.75× to 2×.
- Browser-native three-band Web Audio EQ.
- Flat, Voice, Warm and Bright presets.
- Manual bass, mids and treble controls.
- Optional locally generated rain ambience or brown noise with level control.

### ADHD-friendly listening

- 25-minute focus sprint timer with pause/resume.
- Focus-line reading mode.
- Large-text mode.
- Reduce-motion mode.
- Read + listen simultaneously with automatic active-line movement.
- Continue-listening state to reduce restart friction.

### Engagement without surveillance

Retention features are intentionally local rather than social-network dependent:

- follow authors and series,
- playlists,
- private activity feed,
- continue listening,
- listening progress,
- focus sessions,
- later-ready structure for reading goals/streaks.

There are no ads, analytics SDKs, cloud accounts or remote social graph requirements in the current app.

## Accepted production voice configuration

- Engine/model: OmniVoice through MLX-Audio, `mlx-community/OmniVoice-bf16`.
- Reference: accepted Stage-1 mixed Tamil/English listening reference, recovered transiently and never shipped in artifacts.
- Synthesis steps: **20**.
- Classifier-free guidance scale: **2.5**.
- Crossfade: **55 ms**.
- Clone-reference tokens encoded once per audiobook session and reused across all chunks.

Rejected/older identity settings remain diagnostic only. In particular, 18 synthesis steps were rejected because human listening dropped substantially in Tamil quality.

## Production engine

The reusable engine lives in `tamil_audiobook/engine.py` with low-level CLI entry point `scripts/generate_audiobook.py`.

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

The Stage-2 engine has met its defined acceptance criteria: human-approved speaker identity and naturalness, one consistent bilingual voice path, local/open-source operation, sustained audiobook throughput below the two-minutes-per-minute ceiling, and memory use well below 3 GiB RSS on Apple Silicon.

The repository now includes the product layer needed to operate that engine from both a CLI and a local media-library UI.

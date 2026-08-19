# Tamil voice quality controls and benchmark

This repository keeps the accepted production voice configuration as the default. Advanced OmniVoice controls are opt-in and exist for controlled listening experiments, not as new production defaults.

## Supported controls in pinned MLX-Audio 0.4.6

The pinned OmniVoice implementation exposes these generation inputs:

- `duration_s`
- `instruct`
- `class_temperature` (upstream default `0.0`)
- `position_temperature` (upstream default `5.0`)
- `layer_penalty_factor` (upstream default `5.0`)
- `t_shift` (upstream default `0.1`)

It does **not** expose a native `speed` argument. ListenLeaf therefore exposes `duration_scale` instead. It mirrors OmniVoice's own duration estimator and passes the scaled result through native `duration_s`:

- `duration_scale < 1.0`: request a shorter/faster utterance
- `duration_scale = 1.0`: request the same duration estimate the pinned MLX path would produce
- `duration_scale > 1.0`: request a longer/slower utterance
- omitted: preserve upstream automatic duration exactly

Safe bounds are intentionally conservative: `0.75..1.35`.

## Narration style

Three modes are available:

- `auto`: keep the semantic P3 role instructions already selected for dialogue, questions, exclamations, headings and lists; ordinary narration stays neutral.
- `neutral`: force `instruct="None"` for all chunks.
- `audiobook`: retain explicit semantic role instructions and add a restrained polished-audiobook instruction to otherwise neutral prose.

All styles retain the same cloned reference tokens. A style does not select another speaker.

## Low-level generation example

```bash
python scripts/generate_audiobook.py \
  --text-file sample.txt \
  --reference reference.wav \
  --reference-text-file reference.txt \
  --output-wav sample.wav \
  --output-mp3 sample.mp3 \
  --report report.json \
  --checkpoint-dir chunks \
  --narration-style auto \
  --class-temperature 0.0 \
  --position-temperature 5.0 \
  --layer-penalty-factor 5.0 \
  --t-shift 0.1
```

Only change one parameter at a time when doing a quality sweep unless the experiment explicitly studies interactions.

## Permanent Tamil voice benchmark

The versioned corpus is stored at:

`benchmarks/tamil_voice_quality.json`

It covers formal Tamil, colloquial Tamil, Chennai-style and Kongu-style conversational constructions, English, Tanglish, code switching, technical terminology, numbers, names, dialogue, questions and emotional sentences.

The benchmark is a **human listening gate**. Automated tests only guarantee corpus coverage and plumbing; they do not claim pronunciation, speaker identity or naturalness success.

List cases:

```bash
python scripts/voice_quality_benchmark.py --list
```

Generate one case:

```bash
python scripts/voice_quality_benchmark.py \
  --case codeswitch-01 \
  --reference reference.wav \
  --reference-text-file reference.txt \
  --output-dir benchmark-output
```

Generate a whole category:

```bash
python scripts/voice_quality_benchmark.py \
  --category tanglish \
  --reference reference.wav \
  --reference-text-file reference.txt \
  --output-dir benchmark-output
```

Each generated case receives its own WAV, MP3, engine report and chunk checkpoints. `manifest.json` records the selected controls and the listening criteria for each case.

## Experiment discipline

For future tuning:

1. Keep the reference voice, text and model revision fixed.
2. Run the same benchmark case IDs before and after a change.
3. Change one generation control at a time when possible.
4. Record the complete control set from the engine report.
5. Treat human listening as authoritative for pronunciation, prosody and speaker identity.
6. Do not promote a new default because it is faster or scores better on an automated metric alone.

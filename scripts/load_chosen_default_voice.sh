#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LIBRARY_ROOT="${TAMIL_AUDIOBOOK_HOME:-$HOME/.tamil_audiobook}"
PRIVATE_ROOT="$LIBRARY_ROOT/private"
AUDIO_TARGET="$PRIVATE_ROOT/voice_reference.wav"
TEXT_TARGET="$PRIVATE_ROOT/voice_reference.txt"
MARKER_TARGET="$PRIVATE_ROOT/accepted_c_reference.json"
EXPECTED_GITHUB_USER="sp4devops"
STAGE1_REPO="sp4devops/tamil-voice-clone"
ACCEPTED_RUN_ID="31974866774"
ACCEPTED_ARTIFACT="voice-001-stage1-apple-silicon-listening-samples"

log() {
  printf '[ListenLeaf voice] %s\n' "$*"
}

fail() {
  printf '[ListenLeaf voice] ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  fail "The accepted Stage-2 voice loader targets Apple Silicon macOS."
fi

command -v brew >/dev/null 2>&1 || fail "Homebrew is required. Install Homebrew first, then rerun this script."

missing=()
command -v gh >/dev/null 2>&1 || missing+=(gh)
command -v ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg)
command -v ffprobe >/dev/null 2>&1 || missing+=(ffmpeg)
if ((${#missing[@]})); then
  packages=()
  for item in "${missing[@]}"; do
    seen=0
    for existing in "${packages[@]:-}"; do
      [[ "$existing" == "$item" ]] && seen=1
    done
    (( seen == 0 )) && packages+=("$item")
  done
  log "Installing required local tools: ${packages[*]}"
  brew install "${packages[@]}"
fi

if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  log "GitHub authentication is required to recover the exact human-approved Candidate-C reference."
  gh auth login --hostname github.com --git-protocol https --web
fi

GITHUB_USER="$(gh api user --jq .login 2>/dev/null || true)"
[[ "$GITHUB_USER" == "$EXPECTED_GITHUB_USER" ]] || fail "GitHub CLI must be authenticated as '$EXPECTED_GITHUB_USER' (current: '${GITHUB_USER:-unknown}')."

# Only trust an existing local reference when it carries the exact Candidate-C marker.
if [[ -s "$AUDIO_TARGET" && -s "$TEXT_TARGET" && -s "$MARKER_TARGET" ]]; then
  if python3 - "$MARKER_TARGET" "$ACCEPTED_RUN_ID" <<'PY'
import json, sys
from pathlib import Path
marker = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
raise SystemExit(0 if str(marker.get('stage1_run_id')) == sys.argv[2] and marker.get('reference') == 'mixed_listening_sample.wav' else 1)
PY
  then
    log "Exact human-approved Candidate-C reference is already installed."
    exit 0
  fi
fi

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/listenleaf-candidate-c.XXXXXX")"
cleanup() { rm -rf "$TMP_ROOT"; }
trap cleanup EXIT INT TERM
chmod 700 "$TMP_ROOT"

log "Recovering human-approved Candidate-C reference from Stage-1 run $ACCEPTED_RUN_ID..."
if ! gh run download "$ACCEPTED_RUN_ID" \
  --repo "$STAGE1_REPO" \
  --name "$ACCEPTED_ARTIFACT" \
  --dir "$TMP_ROOT/download" >/dev/null; then
  fail "Candidate-C artifact could not be downloaded. Do not use the old 4-second source as a substitute."
fi

SOURCE_AUDIO="$(find "$TMP_ROOT/download" -type f -name 'mixed_listening_sample.wav' -print -quit)"
[[ -n "$SOURCE_AUDIO" && -s "$SOURCE_AUDIO" ]] || fail "mixed_listening_sample.wav is missing from the accepted Stage-1 artifact."

# This is the exact text used by the human-approved Candidate-C production regression.
# Keep it local and do not echo it into terminal logs.
printf '%s' 'வணக்கம், this is my voice. இன்று Kubernetes சரியாக வேலை செய்கிறது.' > "$TMP_ROOT/reference.txt"

# Normalize the retained artifact to the exact local runtime contract without changing content.
ffmpeg -y -hide_banner -loglevel error \
  -i "$SOURCE_AUDIO" -vn -ac 1 -ar 24000 -c:a pcm_s16le \
  "$TMP_ROOT/reference.wav"

python3 - "$TMP_ROOT/reference.wav" "$TMP_ROOT/reference.txt" <<'PY'
import sys
import wave
from pathlib import Path
wav = Path(sys.argv[1])
text = Path(sys.argv[2]).read_text(encoding='utf-8').strip()
with wave.open(str(wav), 'rb') as handle:
    rate = handle.getframerate()
    channels = handle.getnchannels()
    duration = handle.getnframes() / rate
if rate != 24000 or channels != 1:
    raise SystemExit('Candidate-C reference must be 24 kHz mono PCM')
if not 3.0 <= duration <= 20.0:
    raise SystemExit(f'Unexpected Candidate-C reference duration: {duration:.2f}s')
if len(text) < 20 or not any('\u0b80' <= ch <= '\u0bff' for ch in text) or not any('a' <= ch.lower() <= 'z' for ch in text):
    raise SystemExit('Candidate-C bilingual reference transcript validation failed')
print(f'Candidate-C reference validation=PASS ({duration:.2f}s, 24 kHz mono)')
PY

mkdir -p "$PRIVATE_ROOT"
chmod 700 "$PRIVATE_ROOT"
install -m 600 "$TMP_ROOT/reference.wav" "$AUDIO_TARGET"
install -m 600 "$TMP_ROOT/reference.txt" "$TEXT_TARGET"
python3 - "$MARKER_TARGET" "$ACCEPTED_RUN_ID" "$ACCEPTED_ARTIFACT" <<'PY'
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    'voice': 'human-approved-candidate-c',
    'stage1_run_id': sys.argv[2],
    'artifact': sys.argv[3],
    'reference': 'mixed_listening_sample.wav',
    'num_steps': 20,
    'guidance_scale': 2.5,
}, indent=2), encoding='utf-8')
PY
chmod 600 "$MARKER_TARGET"

log "Human-approved Candidate-C reference is installed locally."
log "The old 4-second original-source reference has been replaced for Stage-2 synthesis."

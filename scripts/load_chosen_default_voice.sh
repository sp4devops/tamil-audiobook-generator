#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LIBRARY_ROOT="${TAMIL_AUDIOBOOK_HOME:-$HOME/.tamil_audiobook}"
AUDIO_TARGET="$LIBRARY_ROOT/private/voice_reference.wav"
TEXT_TARGET="$LIBRARY_ROOT/private/voice_reference.txt"
EXPECTED_GITHUB_USER="sp4devops"

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

if [[ -s "$AUDIO_TARGET" && -s "$TEXT_TARGET" ]]; then
  log "Chosen default voice is already installed locally."
  log "Audio: $AUDIO_TARGET"
  exit 0
fi

command -v brew >/dev/null 2>&1 || fail "Homebrew is required. Install Homebrew first, then rerun this script."

missing=()
command -v gh >/dev/null 2>&1 || missing+=(gh)
command -v age >/dev/null 2>&1 || missing+=(age)
command -v age-keygen >/dev/null 2>&1 || missing+=(age)
command -v ffmpeg >/dev/null 2>&1 || missing+=(ffmpeg)
command -v ffprobe >/dev/null 2>&1 || missing+=(ffmpeg)

if ((${#missing[@]})); then
  # De-duplicate package names before asking Homebrew to install them.
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
  log "GitHub authentication is required only to recover your protected Stage-1 reference."
  log "Opening GitHub's secure browser login now."
  gh auth login --hostname github.com --git-protocol https --web
fi

GITHUB_USER="$(gh api user --jq .login 2>/dev/null || true)"
[[ -n "$GITHUB_USER" ]] || fail "GitHub authentication succeeded but the account could not be identified."
[[ "$GITHUB_USER" == "$EXPECTED_GITHUB_USER" ]] || fail "GitHub CLI is authenticated as '$GITHUB_USER'. The protected voice workflow only permits '$EXPECTED_GITHUB_USER'. Run 'gh auth logout --hostname github.com' and rerun this loader."

log "Authenticated as $GITHUB_USER. Recovering the exact accepted production reference securely..."
if ! bash "$REPO_ROOT/scripts/provision_original_voice.sh" --library "$LIBRARY_ROOT"; then
  fail "Secure provisioning failed. The accepted voice was not replaced with a fallback. Review the provisioning error above."
fi

[[ -s "$AUDIO_TARGET" ]] || fail "Provisioning returned success but voice_reference.wav is missing."
[[ -s "$TEXT_TARGET" ]] || fail "Provisioning returned success but voice_reference.txt is missing."

python3 - "$AUDIO_TARGET" "$TEXT_TARGET" <<'PY'
import sys
import wave
from pathlib import Path

wav_path = Path(sys.argv[1])
text_path = Path(sys.argv[2])
text = text_path.read_text(encoding="utf-8").strip()

with wave.open(str(wav_path), "rb") as handle:
    sample_rate = handle.getframerate()
    channels = handle.getnchannels()
    duration = handle.getnframes() / sample_rate

if sample_rate != 24000 or channels != 1:
    raise SystemExit("Installed voice must be 24 kHz mono PCM WAV")
if not 4.2 <= duration <= 4.9:
    raise SystemExit("Installed voice duration does not match the protected accepted reference")
if len(text) < 8 or not any("\u0b80" <= ch <= "\u0bff" for ch in text):
    raise SystemExit("Installed transcript does not match the expected bilingual/Tamil reference contract")

print(f"Installed voice validation=PASS ({duration:.2f}s, {sample_rate} Hz, mono)")
PY

log "Chosen Stage-2 default voice is loaded and ready."
log "Restart ListenLeaf if it is already open, then Settings should show: Original source voice is configured locally."

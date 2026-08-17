#!/usr/bin/env bash
set -euo pipefail

STAGE1_REPO="sp4devops/tamil-voice-clone"
WORKFLOW="voice-001-provision-device.yml"
LIBRARY_ROOT="${TAMIL_AUDIOBOOK_HOME:-$HOME/.tamil_audiobook}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --library)
      LIBRARY_ROOT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Original-voice provisioning currently targets Apple Silicon macOS." >&2
  exit 1
fi

for tool in gh age-keygen age tar ffmpeg ffprobe; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required provisioning tool: $tool" >&2
    exit 1
  fi
done

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run 'gh auth login' once, then restart ListenLeaf." >&2
  exit 1
fi

PRIVATE_ROOT="$LIBRARY_ROOT/private"
AUDIO_TARGET="$PRIVATE_ROOT/voice_reference.wav"
TEXT_TARGET="$PRIVATE_ROOT/voice_reference.txt"

if [[ -s "$AUDIO_TARGET" && -s "$TEXT_TARGET" ]]; then
  echo "Original source voice is already provisioned locally."
  exit 0
fi

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/listenleaf-voice.XXXXXX")"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT INT TERM
chmod 700 "$TMP_ROOT"

KEY_FILE="$TMP_ROOT/device-age-key.txt"
age-keygen -o "$KEY_FILE" >/dev/null 2>&1
chmod 600 "$KEY_FILE"
RECIPIENT="$(age-keygen -y "$KEY_FILE")"
REQUEST_ID="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(8))
PY
)"

START_EPOCH="$(date +%s)"
echo "Securely provisioning the original source voice for this Mac…"
gh workflow run "$WORKFLOW" \
  --repo "$STAGE1_REPO" \
  --ref main \
  -f "device_recipient=$RECIPIENT" \
  -f "request_id=$REQUEST_ID"

RUN_ID=""
for _ in {1..30}; do
  RUN_ID="$(gh run list \
    --repo "$STAGE1_REPO" \
    --workflow "$WORKFLOW" \
    --event workflow_dispatch \
    --limit 20 \
    --json databaseId,displayTitle,createdAt \
    --jq ".[] | select(.displayTitle == \"Provision original voice $REQUEST_ID\") | .databaseId" \
    | head -n 1)"
  if [[ -n "$RUN_ID" ]]; then
    break
  fi
  sleep 2
done

if [[ -z "$RUN_ID" ]]; then
  echo "Could not locate the secure provisioning workflow run." >&2
  exit 1
fi

gh run watch "$RUN_ID" --repo "$STAGE1_REPO" --exit-status >/dev/null

gh run download "$RUN_ID" \
  --repo "$STAGE1_REPO" \
  --name "original-voice-$REQUEST_ID" \
  --dir "$TMP_ROOT/download" >/dev/null

ENCRYPTED="$TMP_ROOT/download/original-voice-$REQUEST_ID.tar.gz.age"
ARCHIVE="$TMP_ROOT/original-reference.tar.gz"
EXTRACTED="$TMP_ROOT/extracted"
test -s "$ENCRYPTED"
mkdir -p "$EXTRACTED"
age -d -i "$KEY_FILE" -o "$ARCHIVE" "$ENCRYPTED"
tar -xzf "$ARCHIVE" -C "$EXTRACTED"

test -s "$EXTRACTED/reference.wav"
test -s "$EXTRACTED/reference.txt"

# Validate without printing protected transcript content.
python3 - "$EXTRACTED/reference.wav" "$EXTRACTED/reference.txt" <<'PY'
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
    raise SystemExit('Provisioned original voice must be 24 kHz mono PCM')
if not 4.2 <= duration <= 4.9:
    raise SystemExit('Provisioned original voice duration validation failed')
if len(text) < 8 or not any('\u0b80' <= ch <= '\u0bff' for ch in text):
    raise SystemExit('Provisioned original transcript validation failed')
print('Original source voice validation=PASS')
PY

mkdir -p "$PRIVATE_ROOT"
chmod 700 "$PRIVATE_ROOT"
install -m 600 "$EXTRACTED/reference.wav" "$AUDIO_TARGET"
install -m 600 "$EXTRACTED/reference.txt" "$TEXT_TARGET"

# Verify the installed copies, again without exposing transcript text.
test -s "$AUDIO_TARGET"
test -s "$TEXT_TARGET"
echo "Default voice provisioned: original source (local/private)."

#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script targets macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Apple Silicon (arm64) is required." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required for the local ListenLeaf setup." >&2
  exit 1
fi

if ! command -v python3.11 >/dev/null 2>&1; then
  brew install python@3.11
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  brew install ffmpeg
fi
if ! command -v gh >/dev/null 2>&1; then
  brew install gh
fi

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r stage2_requirements.txt
python -m pytest -q tests/test_engine.py tests/test_benchmark_contract.py tests/test_voice.py

if gh auth status >/dev/null 2>&1; then
  if ! bash scripts/load_chosen_default_voice.sh; then
    echo "Warning: the human-approved Candidate-C voice could not be installed. ListenLeaf will retry on startup and generation will stay unavailable until it succeeds or a voice is configured manually." >&2
  fi
else
  echo "The human-approved Candidate-C voice still needs one-time GitHub authentication." >&2
  echo "Run: gh auth login" >&2
  echo "Then start ListenLeaf; it will retry the accepted voice installation automatically." >&2
fi

echo "Stage 2 local environment is ready."
echo "Activate it with: source .venv/bin/activate"
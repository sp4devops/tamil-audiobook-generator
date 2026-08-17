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

if ! command -v python3.11 >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Python 3.11 is required. Install Homebrew/Python 3.11 first." >&2
    exit 1
  fi
  brew install python@3.11
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "FFmpeg is required and Homebrew is unavailable." >&2
    exit 1
  fi
  brew install ffmpeg
fi

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r stage2_requirements.txt
python -m pytest -q tests/test_engine.py tests/test_benchmark_contract.py

echo "Stage 2 local environment is ready."
echo "Activate it with: source .venv/bin/activate"

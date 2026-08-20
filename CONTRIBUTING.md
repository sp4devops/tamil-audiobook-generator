# Contributing to tamil-audiobook-generator

Thanks for considering a contribution.

This project focuses on local-first Tamil, English, and Tanglish audiobook generation on Apple Silicon, with particular attention to speaker consistency, pronunciation, long-form continuity, privacy, and low memory use.

## Before you start

- Open an issue for substantial features or architectural changes before implementing them.
- Keep changes focused and easy to review.
- Do not include private voice references, generated personal audio, API keys, tokens, credentials, or user library data in commits, issues, pull requests, or CI artifacts.
- Preserve the local-first design. New cloud or paid runtime dependencies should not be introduced without prior discussion.
- Audio-quality claims require human listening; automated metrics alone are not sufficient.

## Development setup

On Apple Silicon:

```bash
git clone https://github.com/sp4devops/tamil-audiobook-generator.git
cd tamil-audiobook-generator
bash scripts/setup_macos.sh
source .venv/bin/activate
```

## Tests

Run the relevant test suite before submitting a pull request:

```bash
python -m pytest
ruff check .
```

If your change affects the browser UI, run the repository's browser/E2E checks as well. If it affects synthesis, pronunciation, prosody, speaker identity, memory use, or generation speed, include the relevant Apple-Silicon validation evidence and clearly mark listening quality as human-reviewed or unreviewed.

## Pull requests

A good pull request should:

- explain the problem and why the change is needed;
- keep unrelated refactors out of the same PR;
- include regression tests where practical;
- preserve existing privacy and local-only guarantees;
- document observable behavior changes;
- avoid committing generated audio or private voice material unless it is explicitly safe and redistributable;
- state any model, package, or license implications.

## Licensing

By contributing, you agree that your contributions may be distributed under the repository's MIT License.

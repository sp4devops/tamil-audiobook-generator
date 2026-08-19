#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

# Long-form generation on an 8 GB M2 can otherwise keep Metal saturated for
# hours. Cool mode inserts 5-second idle gaps between newly generated chunks.
# Users can still explicitly override this environment variable to balanced or
# fast before launching.
os.environ.setdefault("LISTENLEAF_GENERATION_MODE", "cool")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tamil_audiobook.controlled_engine import synthesize_audiobook_with_controls
from tamil_audiobook.engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS
from tamil_audiobook.generation_controls import OmniVoiceGenerationControls
from tamil_audiobook.library import LocalLibrary


def _provision_original_voice(lib: LocalLibrary, *, quiet: bool = False) -> bool:
    """Install the human-approved Candidate-C profile used by Stage 2.

    The older short original-source provisioner is intentionally not used here:
    it is not the profile that passed the Stage-2 human quality gate.
    """
    accepted_marker = lib.private_root / "accepted_c_reference.json"
    manual_marker = lib.private_root / "manual_voice_reference.json"
    if lib.voice_ready() and (accepted_marker.is_file() or manual_marker.is_file()):
        return True

    script = REPO_ROOT / "scripts" / "load_chosen_default_voice.sh"
    if not script.is_file():
        if not quiet:
            print("Accepted Candidate-C voice loader is missing from this checkout.", file=sys.stderr)
        return False
    if not quiet:
        print("Accepted Candidate-C voice is not configured; starting secure one-time installation…")
    env = os.environ.copy()
    env["TAMIL_AUDIOBOOK_HOME"] = str(lib.root)
    result = subprocess.run(
        ["bash", str(script)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    ready = result.returncode == 0 and lib.voice_ready() and accepted_marker.is_file()
    if not ready and not quiet:
        print(
            "Accepted voice is still unavailable. Authenticate once with 'gh auth login' or add a manual reference in Settings.",
            file=sys.stderr,
        )
    return ready


def _is_loopback_host(host: str) -> bool:
    value = host.strip().lower()
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(prog="audiobook", description="Local Tamil/English audiobook library and player")
    parser.add_argument("--library", type=Path, help="Override the local library root")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="Import PDF/TXT/Markdown into the local library")
    imp.add_argument("file", type=Path)
    imp.add_argument("--title")
    imp.add_argument("--author", default="Unknown author")
    imp.add_argument("--series", default="")

    sub.add_parser("list", help="List imported books")
    info = sub.add_parser("info", help="Show a book")
    info.add_argument("book_id")

    voice = sub.add_parser("voice", help="Configure a private local voice reference")
    voice.add_argument("audio", type=Path)
    voice.add_argument("transcript_file", type=Path)
    sub.add_parser("provision-voice", help="Securely install the human-approved Candidate-C Stage-2 voice")

    gen = sub.add_parser("generate", help="Generate an audiobook using the accepted C voice settings")
    gen.add_argument("book_id")
    gen.add_argument("--narration-style", choices=("auto", "neutral", "audiobook"), default="auto")
    gen.add_argument(
        "--duration-scale",
        type=float,
        help="Opt-in native duration multiplier: <1.0 shorter/faster, >1.0 longer/slower; 0.75..1.35",
    )
    gen.add_argument("--class-temperature", type=float, default=0.0)
    gen.add_argument("--position-temperature", type=float, default=5.0)
    gen.add_argument("--layer-penalty-factor", type=float, default=5.0)
    gen.add_argument("--t-shift", type=float, default=0.1)

    serve = sub.add_parser("serve", help="Launch the local Spotify-style web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-open", action="store_true")
    serve.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly allow binding the unauthenticated local app to a non-loopback host",
    )

    args = parser.parse_args()
    lib = LocalLibrary(args.library)

    if args.command == "import":
        book = lib.import_book(args.file, title=args.title, author=args.author, series=args.series)
        print(json.dumps(book, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list":
        books = lib.list_books()
        if not books:
            print("No books imported.")
            return 0
        for book in books:
            status = "audio" if book["has_audio"] else "text"
            print(f"{book['id']}  [{status:5}]  {book['title']} — {book['author']}")
        return 0

    if args.command == "info":
        print(json.dumps(lib.get_book(args.book_id), ensure_ascii=False, indent=2))
        return 0

    if args.command == "voice":
        transcript = args.transcript_file.read_text(encoding="utf-8").strip()
        if args.audio.suffix.lower() != ".wav":
            raise SystemExit("CLI voice setup currently requires a 24 kHz mono WAV; the UI accepts common audio formats and converts locally.")
        lib.save_voice_reference(args.audio, transcript)
        print(f"Voice reference configured locally at {lib.private_root}")
        return 0

    if args.command == "provision-voice":
        return 0 if _provision_original_voice(lib) else 1

    if args.command == "generate":
        if not _provision_original_voice(lib):
            raise SystemExit("Accepted Candidate-C or manually configured source voice is unavailable. Secure provisioning did not complete.")
        book = lib.get_book(args.book_id)
        ref_audio, ref_text = lib.voice_reference_paths()
        book_dir = lib._book_dir(args.book_id)
        controls = OmniVoiceGenerationControls(
            narration_style=args.narration_style,
            duration_scale=args.duration_scale,
            class_temperature=args.class_temperature,
            position_temperature=args.position_temperature,
            layer_penalty_factor=args.layer_penalty_factor,
            t_shift=args.t_shift,
        ).validated()
        report = synthesize_audiobook_with_controls(
            controls=controls,
            text=lib.text(args.book_id),
            reference_audio=ref_audio,
            reference_text=ref_text.read_text(encoding="utf-8").strip(),
            output_wav=book_dir / "audiobook.wav",
            output_mp3=book_dir / "audiobook.mp3",
            num_steps=DEFAULT_NUM_STEPS,
            guidance_scale=DEFAULT_GUIDANCE_SCALE,
            report_path=book_dir / "report.json",
            checkpoint_dir=book_dir / "chunks",
        )
        lib.build_cues(args.book_id, report)
        (book_dir / "audiobook.wav").unlink(missing_ok=True)
        print(f"Generated: {book['title']}")
        print(f"Audio: {lib.audio_path(args.book_id)}")
        print(f"Duration: {report['audio_seconds']:.1f}s  RTF: {report['aggregate_rtf']:.3f}")
        print(f"OmniVoice controls: {json.dumps(report['omnivoice_controls'], separators=(',', ':'))}")
        return 0

    if args.command == "serve":
        import threading
        import webbrowser
        import uvicorn

        if not _is_loopback_host(args.host) and not args.allow_network:
            raise SystemExit(
                "Refusing to expose the unauthenticated local library on a non-loopback host. "
                "Use --allow-network only if you understand that library and destructive API endpoints become reachable on that interface."
            )
        if args.library:
            os.environ["TAMIL_AUDIOBOOK_HOME"] = str(args.library.expanduser().resolve())
        # Provision before FastAPI imports its process-global LocalLibrary instance.
        # Failure is non-fatal: the UI still launches and Settings remains available.
        _provision_original_voice(lib)
        url = f"http://{args.host}:{args.port}"
        if not args.no_open:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        uvicorn.run("tamil_audiobook.app:app", host=args.host, port=args.port, reload=False)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

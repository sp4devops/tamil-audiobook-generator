from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .controlled_engine import synthesize_audiobook_with_controls
from .engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS, GenerationCancelled
from .generation_controls import OmniVoiceGenerationControls
from .library import LocalLibrary
from .locking import GenerationLock
from .voice import normalize_reference_audio, resolve_voice

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
os.environ.setdefault("LISTENLEAF_GENERATION_MODE", "cool")


def _provision_original_voice(lib: LocalLibrary, *, quiet: bool = False) -> bool:
    accepted_marker = lib.private_root / "accepted_c_reference.json"
    manual_marker = lib.private_root / "manual_voice_reference.json"
    if lib.voice_ready() and (accepted_marker.is_file() or manual_marker.is_file()):
        return True
    script = REPO_ROOT / "scripts" / "load_chosen_default_voice.sh"
    if not script.is_file():
        if not quiet:
            print("Accepted Candidate-C voice loader is missing from this installation.", file=sys.stderr)
        return False
    if not quiet:
        print("Accepted Candidate-C voice is not configured; starting secure one-time installation…")
    env = os.environ.copy()
    env["TAMIL_AUDIOBOOK_HOME"] = str(lib.root)
    result = subprocess.run(["bash", str(script)], cwd=REPO_ROOT, env=env, check=False)
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


def _configure_voice(lib: LocalLibrary, source: Path, transcript: str) -> None:
    if not transcript.strip():
        raise SystemExit("Reference transcript is required")
    lib.private_root.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="voice-cli-", suffix=".wav", dir=lib.private_root)
    os.close(fd)
    normalized = Path(temp_name)
    normalized.unlink(missing_ok=True)
    try:
        report = normalize_reference_audio(source, normalized)
        lib.save_voice_reference(normalized, transcript)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        normalized.unlink(missing_ok=True)
    print(
        f"Voice reference configured locally at {lib.private_root} "
        f"({report.duration_seconds:.1f}s, 24 kHz mono)"
    )


def _generate(lib: LocalLibrary, args: argparse.Namespace) -> int:
    if not _provision_original_voice(lib):
        raise SystemExit(
            "Accepted Candidate-C or manually configured source voice is unavailable. Secure provisioning did not complete."
        )
    lock = GenerationLock(lib.root)
    if not lock.try_acquire():
        raise SystemExit(
            "Another synthesis process already owns this library's generation lock. "
            "Wait for it to finish or cancel it before starting another job."
        )
    try:
        book = lib.get_book(args.book_id)
        ref_audio, ref_text, _ = resolve_voice(lib)
        book_dir = lib._book_dir(args.book_id)
        controls = OmniVoiceGenerationControls(
            narration_style=args.narration_style,
            duration_scale=args.duration_scale,
            class_temperature=args.class_temperature,
            position_temperature=args.position_temperature,
            layer_penalty_factor=args.layer_penalty_factor,
            t_shift=args.t_shift,
        ).validated()
        try:
            report = synthesize_audiobook_with_controls(
                controls=controls,
                text=lib.text(args.book_id),
                reference_audio=ref_audio,
                reference_text=ref_text,
                output_wav=book_dir / "audiobook.wav",
                output_mp3=book_dir / "audiobook.mp3",
                num_steps=DEFAULT_NUM_STEPS,
                guidance_scale=DEFAULT_GUIDANCE_SCALE,
                report_path=book_dir / "report.json",
                checkpoint_dir=book_dir / "chunks",
            )
        except KeyboardInterrupt:
            print("\nGeneration interrupted. Completed checkpoints were kept and can be resumed.", file=sys.stderr)
            return 130
        except GenerationCancelled:
            print("Generation cancelled. Completed checkpoints were kept and can be resumed.", file=sys.stderr)
            return 130
        lib.build_cues(args.book_id, report)
        (book_dir / "audiobook.wav").unlink(missing_ok=True)
        print(f"Generated: {book['title']}")
        print(f"Audio: {lib.audio_path(args.book_id)}")
        print(f"Duration: {report['audio_seconds']:.1f}s  RTF: {report['aggregate_rtf']:.3f}")
        print(f"OmniVoice controls: {json.dumps(report['omnivoice_controls'], separators=(',', ':'))}")
        return 0
    finally:
        lock.release()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="listenleaf", description="Local Tamil/English audiobook library and player")
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

    gen = sub.add_parser("generate", help="Generate an audiobook using the configured source voice")
    gen.add_argument("book_id")
    gen.add_argument("--narration-style", choices=("auto", "neutral", "audiobook"), default="auto")
    gen.add_argument("--duration-scale", type=float)
    gen.add_argument("--class-temperature", type=float, default=0.0)
    gen.add_argument("--position-temperature", type=float, default=5.0)
    gen.add_argument("--layer-penalty-factor", type=float, default=5.0)
    gen.add_argument("--t-shift", type=float, default=0.1)

    serve = sub.add_parser("serve", help="Launch the local web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-open", action="store_true")
    serve.add_argument("--allow-network", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lib = LocalLibrary(args.library)
    if args.command == "import":
        print(json.dumps(lib.import_book(args.file, title=args.title, author=args.author, series=args.series), ensure_ascii=False, indent=2))
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
        _configure_voice(lib, args.audio, args.transcript_file.read_text(encoding="utf-8").strip())
        return 0
    if args.command == "provision-voice":
        return 0 if _provision_original_voice(lib) else 1
    if args.command == "generate":
        return _generate(lib, args)
    if args.command == "serve":
        import threading
        import webbrowser
        import uvicorn

        if not _is_loopback_host(args.host) and not args.allow_network:
            raise SystemExit(
                "Refusing to expose the unauthenticated local library on a non-loopback host. "
                "Use --allow-network only if you understand the risk."
            )
        if args.library:
            os.environ["TAMIL_AUDIOBOOK_HOME"] = str(args.library.expanduser().resolve())
        _provision_original_voice(lib)
        url = f"http://{args.host}:{args.port}"
        if not args.no_open:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        uvicorn.run("tamil_audiobook.app:app", host=args.host, port=args.port, reload=False)
        return 0
    return 1

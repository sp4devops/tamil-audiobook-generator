#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tamil_audiobook.engine import DEFAULT_GUIDANCE_SCALE, DEFAULT_NUM_STEPS, synthesize_audiobook
from tamil_audiobook.library import LocalLibrary
from tamil_audiobook.textnorm import normalize_book_text


# Keep normalization at the library read boundary for the normal CLI/UI launch
# path. This makes existing imported books, future imports, estimates, cue
# building and TTS all consume the same repaired Unicode without rewriting the
# user's source PDF. The raw source copy remains untouched.
_RAW_LIBRARY_TEXT = LocalLibrary.text


def _normalized_library_text(self: LocalLibrary, book_id: str) -> str:
    return normalize_book_text(_RAW_LIBRARY_TEXT(self, book_id))


if LocalLibrary.text is not _normalized_library_text:
    LocalLibrary.text = _normalized_library_text


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

    voice = sub.add_parser("voice", help="Configure the private local voice reference")
    voice.add_argument("audio", type=Path)
    voice.add_argument("transcript_file", type=Path)

    gen = sub.add_parser("generate", help="Generate an audiobook using the accepted C voice settings")
    gen.add_argument("book_id")

    serve = sub.add_parser("serve", help="Launch the local Spotify-style web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-open", action="store_true")

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

    if args.command == "generate":
        if not lib.voice_ready():
            raise SystemExit("Voice reference is not configured. Run: audiobook voice REFERENCE.wav TRANSCRIPT.txt")
        book = lib.get_book(args.book_id)
        ref_audio, ref_text = lib.voice_reference_paths()
        book_dir = lib._book_dir(args.book_id)
        report = synthesize_audiobook(
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
        return 0

    if args.command == "serve":
        import os
        import threading
        import webbrowser
        import uvicorn

        if args.library:
            os.environ["TAMIL_AUDIOBOOK_HOME"] = str(args.library.expanduser().resolve())
        url = f"http://{args.host}:{args.port}"
        if not args.no_open:
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        uvicorn.run("tamil_audiobook.app:app", host=args.host, port=args.port, reload=False)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line interface for md-image-oss."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Config, load_env_file
from .processor import HtmlProcessor, MarkdownProcessor
from .uploader import OSSUploader

_MARKDOWN_SUFFIXES = {".md", ".mdx", ".markdown"}
_HTML_SUFFIXES = {".html", ".htm"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-oss",
        description=(
            "Upload all images referenced in a Markdown / MDX / HTML document "
            "to Aliyun OSS, compress them first, and rewrite the document."
        ),
        epilog=(
            "All OSS credentials are read from environment variables — see "
            ".env.example. Use --env-file to load them from a file."
        ),
    )
    parser.add_argument(
        "input",
        help="Path to the input document (.md, .mdx, .html, .htm).",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output path. Defaults to <input>.oss<ext>.",
    )
    parser.add_argument(
        "-i", "--in-place",
        action="store_true",
        help="Overwrite the original file in place.",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="Skip the image compression step.",
    )
    parser.add_argument(
        "-q", "--quality",
        type=int, default=85, metavar="N",
        help="JPEG / WebP quality, 1–100 (default: 85).",
    )
    parser.add_argument(
        "--process-remote",
        action="store_true",
        help="Also re-upload images already hosted at remote URLs.",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help="Load environment variables from this file before running.",
    )
    parser.add_argument(
        "--quiet", "-Q",
        action="store_true",
        help="Suppress per-image progress logs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process without writing the output file. Useful for previewing.",
    )
    parser.add_argument(
        "--no-obsidian",
        action="store_true",
        help="Disable parsing of Obsidian wikilink image syntax (![[image.png]]).",
    )
    parser.add_argument(
        "--obsidian-vault",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Explicit Obsidian vault root used to resolve ![[filename]] when the "
            "file is not next to the note. Skips auto-detection of .obsidian/."
        ),
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.env_file:
        loaded = load_env_file(args.env_file)
        if not args.quiet:
            print(f"Loaded {loaded} environment variables from {args.env_file}",
                  file=sys.stderr)

    if not 1 <= args.quality <= 100:
        print("Error: --quality must be between 1 and 100.", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    suffix = input_path.suffix.lower()
    if suffix in _MARKDOWN_SUFFIXES:
        processor_cls = MarkdownProcessor
    elif suffix in _HTML_SUFFIXES:
        processor_cls = HtmlProcessor
    else:
        print(
            f"Error: unsupported file type '{suffix}'. "
            f"Supported: {', '.join(sorted(_MARKDOWN_SUFFIXES | _HTML_SUFFIXES))}.",
            file=sys.stderr,
        )
        return 2

    if args.in_place and args.output:
        print("Error: --in-place and --output are mutually exclusive.", file=sys.stderr)
        return 2

    if args.in_place:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(input_path.stem + ".oss" + input_path.suffix)

    try:
        config = Config.from_env()
    except EnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Tip: copy .env.example to .env and fill in your OSS credentials, "
              "then re-run with --env-file .env", file=sys.stderr)
        return 1

    if args.obsidian_vault is not None and not args.obsidian_vault.is_dir():
        print(
            f"Error: --obsidian-vault path is not a directory: {args.obsidian_vault}",
            file=sys.stderr,
        )
        return 2

    uploader = OSSUploader(config)
    processor = processor_cls(
        uploader=uploader,
        compress=not args.no_compress,
        quality=args.quality,
        process_remote=args.process_remote,
        verbose=not args.quiet,
        obsidian=not args.no_obsidian,
        obsidian_vault=args.obsidian_vault,
    )

    if not args.quiet:
        print(f"📖 Reading {input_path}", file=sys.stderr)
    content = input_path.read_text(encoding="utf-8")

    if not args.quiet:
        print("🔄 Processing images...", file=sys.stderr)
    new_content = processor.process(content, input_path.parent)

    if args.dry_run:
        if not args.quiet:
            print("🌵 Dry run — output not written.", file=sys.stderr)
        sys.stdout.write(new_content)
    else:
        if not args.quiet:
            verb = "Overwriting" if output_path == input_path else "Writing"
            print(f"💾 {verb} {output_path}", file=sys.stderr)
        output_path.write_text(new_content, encoding="utf-8")

    if not args.quiet:
        s = processor.stats
        print(
            f"✨ Done. found={s['found']} uploaded={s['uploaded']} "
            f"skipped={s['skipped']} failed={s['failed']}",
            file=sys.stderr,
        )

    return 0 if processor.stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

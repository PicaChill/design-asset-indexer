"""Command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .archive import DEFAULT_MAX_ENTRIES
from .inventory import scan_directory
from .previews import create_contact_sheet


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="design-asset-index",
        description="Offline, read-only design asset archive indexing.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    scan = subcommands.add_parser("scan", help="scan an input directory")
    scan.add_argument("input_dir", type=Path)
    scan.add_argument("--out", required=True, type=Path, dest="output_dir")
    scan.add_argument(
        "--max-zip-entries",
        type=int,
        default=DEFAULT_MAX_ENTRIES,
        help="maximum entries accepted in one ZIP archive",
    )

    contact = subcommands.add_parser("contact-sheet", help="build a contact sheet from preview images")
    contact.add_argument("preview_dir", type=Path)
    contact.add_argument("--out", required=True, type=Path, dest="output_file")
    contact.add_argument("--columns", type=int, default=4)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            if args.max_zip_entries < 1:
                raise ValueError("maximum ZIP entry count must be positive")
            summary = scan_directory(
                args.input_dir,
                args.output_dir,
                max_zip_entries=args.max_zip_entries,
            )
            print(json.dumps(summary, sort_keys=True))
            return 0
        count = create_contact_sheet(args.preview_dir, args.output_file, columns=args.columns)
        print(json.dumps({"images": count}, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

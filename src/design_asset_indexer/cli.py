"""Command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .archive import DEFAULT_MAX_ENTRIES
from .inventory import scan_directory
from .photoshop import PhotoshopAdapter, PhotoshopAutomationError, PhotoshopUnavailableError
from .previews import create_contact_sheet
from .signatures import inspect_signatures, replace_signatures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="design-asset-index",
        description="Offline design asset indexing and copied-output PSD processing.",
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

    signature_inspect = subcommands.add_parser(
        "signature-inspect",
        help="inspect PSD text layers through locally installed Photoshop",
    )
    signature_inspect.add_argument("input_dir", metavar="INPUT", type=Path)
    signature_inspect.add_argument("--out", required=True, type=Path, dest="output_dir")
    signature_inspect.add_argument("--recursive", action="store_true")
    signature_inspect.add_argument("--include", default="*.psd")
    signature_inspect.add_argument("--layer-name")
    signature_inspect.add_argument("--contains-text")
    signature_inspect.add_argument("--max-files", type=int, default=100)

    signature_replace = subcommands.add_parser(
        "signature-replace",
        help="replace one exact PSD text match in a copied output file",
    )
    signature_replace.add_argument("input_dir", metavar="INPUT", type=Path)
    signature_replace.add_argument("--out", required=True, type=Path, dest="output_dir")
    signature_replace.add_argument("--from", required=True, dest="old_text")
    signature_replace.add_argument("--to", required=True, dest="new_text")
    signature_replace.add_argument("--layer-name")
    signature_replace.add_argument("--dry-run", action="store_true")
    signature_replace.add_argument("--recursive", action="store_true")
    signature_replace.add_argument("--include", default="*.psd")
    signature_replace.add_argument("--max-files", type=int, default=100)
    return parser


def _photoshop_adapter() -> PhotoshopAdapter:
    adapter = PhotoshopAdapter()
    if not adapter.is_available():
        raise PhotoshopUnavailableError("Adobe Photoshop automation is unavailable")
    return adapter


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
        if args.command == "contact-sheet":
            count = create_contact_sheet(args.preview_dir, args.output_file, columns=args.columns)
            print(json.dumps({"images": count}, sort_keys=True))
            return 0
        if args.command == "signature-inspect":
            summary = inspect_signatures(
                args.input_dir,
                args.output_dir,
                _photoshop_adapter(),
                recursive=args.recursive,
                include=args.include,
                layer_name=args.layer_name,
                contains_text=args.contains_text,
                max_files=args.max_files,
            )
            print(json.dumps(summary, sort_keys=True))
            return 0
        summary = replace_signatures(
            args.input_dir,
            args.output_dir,
            _photoshop_adapter(),
            old_text=args.old_text,
            new_text=args.new_text,
            layer_name=args.layer_name,
            dry_run=args.dry_run,
            recursive=args.recursive,
            include=args.include,
            max_files=args.max_files,
        )
        print(json.dumps(summary, sort_keys=True))
        return 0
    except PhotoshopAutomationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("error: filesystem operation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

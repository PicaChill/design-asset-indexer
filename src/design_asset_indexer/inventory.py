"""Read-only recursive inventory orchestration."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .archive import DEFAULT_MAX_ENTRIES, index_zip
from .detect import detect_file
from .duplicates import find_duplicate_candidates
from .previews import write_jpeg_preview
from .psd import PSDParseError, parse_psd
from .reports import write_inventory_csv, write_json, write_jsonl


@dataclass(frozen=True)
class InventoryRecord:
    relative_path: str
    size: int
    suffix: str
    detected_type: str
    width: int | None
    height: int | None
    error: str | None


def _stable_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        directories: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    directories.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
            except OSError:
                continue
        directories.sort(key=lambda path: _stable_key(path.relative_to(root).as_posix()), reverse=True)
        stack.extend(directories)
    files.sort(key=lambda path: _stable_key(path.relative_to(root).as_posix()))
    return files


def _validate_roots(input_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    try:
        source = input_dir.resolve(strict=True)
    except OSError as error:
        raise ValueError("input directory is unavailable") from error
    if not source.is_dir():
        raise ValueError("input path is not a directory")
    destination = output_dir.resolve(strict=False)
    if destination == source or destination.is_relative_to(source):
        raise ValueError("output directory must not be inside input directory")
    return source, destination


def _image_dimensions(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        dimensions = image.size
        image.verify()
    return dimensions


def scan_directory(
    input_dir: Path,
    output_dir: Path,
    *,
    max_zip_entries: int = DEFAULT_MAX_ENTRIES,
) -> dict:
    source, destination = _validate_roots(input_dir, output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    archive_records: list[dict] = []
    preview_records: list[dict] = []
    duplicate_inputs: list[tuple[str, Path, int]] = []

    for path in _iter_files(source):
        relative_path = path.relative_to(source).as_posix()
        size = 0
        detected_type = "OTHER"
        width: int | None = None
        height: int | None = None
        error: str | None = None
        try:
            size = path.stat().st_size
            detected_type = detect_file(path)
            duplicate_inputs.append((relative_path, path, size))
            if detected_type in {"PSD", "PSB"}:
                metadata = parse_psd(path)
                width, height = metadata.width, metadata.height
                if metadata.thumbnail_jpeg and metadata.thumbnail_resource_id:
                    try:
                        preview_records.append(
                            write_jpeg_preview(
                                destination,
                                relative_path,
                                metadata.thumbnail_jpeg,
                                metadata.thumbnail_resource_id,
                            )
                        )
                    except ValueError as preview_error:
                        error = type(preview_error).__name__
                elif metadata.thumbnail_error:
                    error = "InvalidThumbnailResource"
            elif detected_type in {"JPEG", "PNG", "GIF"}:
                width, height = _image_dimensions(path)
            elif detected_type == "ZIP":
                archive_record = index_zip(path, relative_path, max_zip_entries)
                archive_records.append(archive_record)
                if archive_record["error"]:
                    error = archive_record["error"]
        except (OSError, PSDParseError, UnidentifiedImageError, ValueError) as scan_error:
            error = type(scan_error).__name__

        records.append(
            asdict(
                InventoryRecord(
                    relative_path=relative_path,
                    size=size,
                    suffix=path.suffix.lower(),
                    detected_type=detected_type,
                    width=width,
                    height=height,
                    error=error,
                )
            )
        )

    records.sort(key=lambda item: _stable_key(item["relative_path"]))
    archive_records.sort(key=lambda item: _stable_key(item["archive_relative_path"]))
    preview_records.sort(key=lambda item: _stable_key(item["relative_path"]))
    duplicates = find_duplicate_candidates(duplicate_inputs)

    write_inventory_csv(destination / "inventory.csv", records)
    write_jsonl(destination / "inventory.jsonl", records)
    write_jsonl(destination / "archives.jsonl", archive_records)
    write_json(destination / "duplicates.json", duplicates)
    write_jsonl(destination / "previews.jsonl", preview_records)

    type_counts = Counter(item["detected_type"] for item in records)
    summary = {
        "archive_count": len(archive_records),
        "duplicate_group_count": len(duplicates["groups"]),
        "error_count": sum(item["error"] is not None for item in records),
        "file_count": len(records),
        "preview_count": len(preview_records),
        "type_counts": dict(sorted(type_counts.items())),
    }
    write_json(destination / "summary.json", summary)
    return summary

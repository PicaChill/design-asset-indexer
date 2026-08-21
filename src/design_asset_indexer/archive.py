"""Read-only ZIP directory indexing."""

from __future__ import annotations

from pathlib import Path
import zipfile


DEFAULT_MAX_ENTRIES = 100_000


def index_zip(path: Path, relative_path: str, max_entries: int = DEFAULT_MAX_ENTRIES) -> dict:
    record: dict = {
        "archive_relative_path": relative_path,
        "entry_count": 0,
        "entries": [],
        "error": None,
    }
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise ValueError("ZIP entry count exceeds safety limit")
            entries = [
                {
                    "name": item.filename,
                    "uncompressed_size": item.file_size,
                    "compressed_size": item.compress_size,
                    "crc32": f"{item.CRC:08x}",
                    "is_directory": item.is_dir(),
                }
                for item in infos
            ]
            entries.sort(key=lambda item: (item["name"].casefold(), item["name"]))
            record["entry_count"] = len(entries)
            record["entries"] = entries
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        record["error"] = type(error).__name__
    return record

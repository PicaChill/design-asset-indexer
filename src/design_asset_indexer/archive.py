"""Read-only ZIP directory indexing."""

from __future__ import annotations

from pathlib import Path
import struct
import zipfile


DEFAULT_MAX_ENTRIES = 100_000
MAX_CENTRAL_DIRECTORY_BYTES = 64 * 1024 * 1024
MAX_EOCD_SEARCH_BYTES = 65_557
EOCD_SIGNATURE = b"PK\x05\x06"


def _preflight_zip(path: Path, max_entries: int) -> None:
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, file_size - MAX_EOCD_SEARCH_BYTES))
        tail = handle.read()
    position = tail.rfind(EOCD_SIGNATURE)
    if position < 0 or len(tail) - position < 22:
        raise zipfile.BadZipFile("missing end-of-central-directory record")
    (
        _signature,
        disk_number,
        directory_disk,
        disk_entries,
        total_entries,
        directory_size,
        directory_offset,
        comment_size,
    ) = struct.unpack("<4s4H2LH", tail[position : position + 22])
    if position + 22 + comment_size > len(tail):
        raise zipfile.BadZipFile("truncated ZIP comment")
    if disk_number or directory_disk or disk_entries != total_entries:
        raise ValueError("multi-disk ZIP archives are not supported")
    if total_entries == 0xFFFF or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
        raise ValueError("ZIP64 directory metadata is outside the v0.1 safety profile")
    if total_entries > max_entries:
        raise ValueError("ZIP entry count exceeds safety limit")
    if directory_size > MAX_CENTRAL_DIRECTORY_BYTES:
        raise ValueError("ZIP central directory exceeds safety limit")
    if directory_offset + directory_size > file_size:
        raise zipfile.BadZipFile("central directory exceeds archive bounds")


def index_zip(path: Path, relative_path: str, max_entries: int = DEFAULT_MAX_ENTRIES) -> dict:
    record: dict = {
        "archive_relative_path": relative_path,
        "entry_count": 0,
        "entries": [],
        "error": None,
    }
    try:
        _preflight_zip(path, max_entries)
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > max_entries:
                raise ValueError("ZIP entry count changed after safety preflight")
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

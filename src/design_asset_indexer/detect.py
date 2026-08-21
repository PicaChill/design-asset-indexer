"""Small signature-based format detector."""

from __future__ import annotations

from pathlib import Path


PSD_SIGNATURE = b"8BPS"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def detect_bytes(header: bytes) -> str:
    """Return a stable type name using magic bytes, not the filename suffix."""

    if header.startswith(PSD_SIGNATURE) and len(header) >= 6:
        version = int.from_bytes(header[4:6], "big")
        if version == 1:
            return "PSD"
        if version == 2:
            return "PSB"
        return "OTHER"
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if header.startswith(PNG_SIGNATURE):
        return "PNG"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "GIF"
    if header.startswith(ZIP_SIGNATURES):
        return "ZIP"
    return "OTHER"


def detect_file(path: Path) -> str:
    with path.open("rb") as handle:
        return detect_bytes(handle.read(16))

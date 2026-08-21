"""Bounded, read-only parsing for the PSD/PSB header and image resources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import struct
from typing import BinaryIO


MAX_RESOURCE_SECTION_BYTES = 256 * 1024 * 1024
MAX_RESOURCE_BLOCKS = 10_000
MAX_THUMBNAIL_BYTES = 32 * 1024 * 1024
THUMBNAIL_RESOURCE_IDS = (1033, 1036)


class PSDParseError(ValueError):
    """A bounded parse failure suitable for a structured inventory error."""


@dataclass(frozen=True)
class PSDMetadata:
    signature: str
    version: int
    channels: int
    width: int
    height: int
    depth: int
    color_mode: int
    thumbnail_jpeg: bytes | None = None
    thumbnail_resource_id: int | None = None
    thumbnail_error: str | None = None


def _read_exact(handle: BinaryIO, size: int, label: str) -> bytes:
    if size < 0:
        raise PSDParseError(f"invalid {label} length")
    data = handle.read(size)
    if len(data) != size:
        raise PSDParseError(f"truncated {label}")
    return data


def _read_u16(handle: BinaryIO, label: str) -> int:
    return struct.unpack(">H", _read_exact(handle, 2, label))[0]


def _read_u32(handle: BinaryIO, label: str) -> int:
    return struct.unpack(">I", _read_exact(handle, 4, label))[0]


def _bounded_skip(handle: BinaryIO, size: int, end: int, label: str) -> None:
    if size < 0 or handle.tell() + size > end:
        raise PSDParseError(f"invalid {label} length")
    handle.seek(size, os.SEEK_CUR)


def _decode_thumbnail(data: bytes) -> tuple[bytes | None, str | None]:
    if len(data) < 28:
        return None, "thumbnail resource is truncated"
    (
        image_format,
        width,
        height,
        _row_bytes,
        _total_size,
        compressed_size,
        bits_per_pixel,
        planes,
    ) = struct.unpack(">6I2H", data[:28])
    if image_format != 1:
        return None, "thumbnail resource is not JPEG"
    if not width or not height or bits_per_pixel != 24 or planes != 1:
        return None, "thumbnail header is invalid"
    payload = data[28:]
    if compressed_size <= 0 or compressed_size > len(payload):
        return None, "thumbnail compressed size is invalid"
    jpeg = payload[:compressed_size]
    if len(jpeg) > MAX_THUMBNAIL_BYTES:
        return None, "thumbnail exceeds safety limit"
    if not jpeg.startswith(b"\xff\xd8\xff"):
        return None, "thumbnail payload is not JPEG"
    return jpeg, None


def parse_psd(path: Path) -> PSDMetadata:
    """Parse only the documented header and image-resource section."""

    file_size = path.stat().st_size
    with path.open("rb") as handle:
        signature = _read_exact(handle, 4, "signature")
        if signature != b"8BPS":
            raise PSDParseError("invalid PSD signature")
        version = _read_u16(handle, "version")
        if version not in (1, 2):
            raise PSDParseError("unsupported PSD version")
        reserved = _read_exact(handle, 6, "reserved header")
        if reserved != b"\x00" * 6:
            raise PSDParseError("reserved header bytes are not zero")
        channels = _read_u16(handle, "channels")
        height = _read_u32(handle, "height")
        width = _read_u32(handle, "width")
        depth = _read_u16(handle, "depth")
        color_mode = _read_u16(handle, "color mode")
        if not 1 <= channels <= 56:
            raise PSDParseError("channel count is outside the supported range")
        if not width or not height:
            raise PSDParseError("canvas dimensions must be positive")

        color_data_size = _read_u32(handle, "color mode section")
        _bounded_skip(handle, color_data_size, file_size, "color mode section")

        resource_size = _read_u32(handle, "image resources section")
        if resource_size > MAX_RESOURCE_SECTION_BYTES:
            raise PSDParseError("image resources section exceeds safety limit")
        resource_end = handle.tell() + resource_size
        if resource_end > file_size:
            raise PSDParseError("truncated image resources section")

        selected_jpeg: bytes | None = None
        selected_id: int | None = None
        thumbnail_error: str | None = None
        blocks = 0
        while handle.tell() < resource_end:
            blocks += 1
            if blocks > MAX_RESOURCE_BLOCKS:
                raise PSDParseError("too many image resource blocks")
            if resource_end - handle.tell() < 12:
                raise PSDParseError("truncated image resource block")
            block_signature = _read_exact(handle, 4, "resource signature")
            if block_signature != b"8BIM":
                raise PSDParseError("invalid image resource signature")
            resource_id = _read_u16(handle, "resource id")

            name_size = _read_exact(handle, 1, "resource name length")[0]
            _bounded_skip(handle, name_size, resource_end, "resource name")
            if (1 + name_size) % 2:
                _bounded_skip(handle, 1, resource_end, "resource name padding")

            data_size = _read_u32(handle, "resource data")
            if data_size > resource_end - handle.tell():
                raise PSDParseError("resource data exceeds section bounds")
            if resource_id in THUMBNAIL_RESOURCE_IDS:
                if data_size > MAX_THUMBNAIL_BYTES + 28:
                    thumbnail_error = "thumbnail resource exceeds safety limit"
                    handle.seek(data_size, os.SEEK_CUR)
                else:
                    data = _read_exact(handle, data_size, "thumbnail resource")
                    jpeg, error = _decode_thumbnail(data)
                    if error:
                        thumbnail_error = error
                    elif jpeg is not None and (selected_id is None or resource_id == 1036):
                        selected_jpeg = jpeg
                        selected_id = resource_id
                        thumbnail_error = None
            else:
                handle.seek(data_size, os.SEEK_CUR)
            if data_size % 2:
                _bounded_skip(handle, 1, resource_end, "resource data padding")

        if handle.tell() != resource_end:
            raise PSDParseError("image resources section ended out of bounds")

    return PSDMetadata(
        signature="8BPS",
        version=version,
        channels=channels,
        width=width,
        height=height,
        depth=depth,
        color_mode=color_mode,
        thumbnail_jpeg=selected_jpeg,
        thumbnail_resource_id=selected_id,
        thumbnail_error=thumbnail_error,
    )

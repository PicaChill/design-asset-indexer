"""Generate every binary fixture used by the test suite."""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import shutil
import struct
import zipfile

from PIL import Image, ImageDraw


def _synthetic_image(size: tuple[int, int], color: tuple[int, int, int], label: str) -> Image.Image:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((6, 6, size[0] - 7, size[1] - 7), outline="white", width=2)
    draw.text((10, 10), label, fill="white")
    return image


def _jpeg_bytes() -> tuple[bytes, int, int]:
    image = _synthetic_image((48, 32), (35, 80, 145), "SYNTHETIC-001")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    image.close()
    return buffer.getvalue(), 48, 32


def _resource_block(resource_id: int, data: bytes) -> bytes:
    name = b"\x00\x00"
    block = b"8BIM" + struct.pack(">H", resource_id) + name + struct.pack(">I", len(data)) + data
    if len(data) % 2:
        block += b"\x00"
    return block


def _psd_bytes(thumbnail: bytes | None = None, width: int = 16, height: int = 12) -> bytes:
    header = (
        b"8BPS"
        + struct.pack(">H", 1)
        + b"\x00" * 6
        + struct.pack(">HIIHH", 3, height, width, 8, 3)
    )
    resources = b""
    if thumbnail is not None:
        thumb_width, thumb_height = 48, 32
        row_bytes = ((thumb_width * 24 + 31) // 32) * 4
        thumb_header = struct.pack(
            ">6I2H",
            1,
            thumb_width,
            thumb_height,
            row_bytes,
            row_bytes * thumb_height,
            len(thumbnail),
            24,
            1,
        )
        resources = _resource_block(1036, thumb_header + thumbnail)
    color_mode = struct.pack(">I", 0)
    resource_section = struct.pack(">I", len(resources)) + resources
    layer_mask = struct.pack(">I", 0)
    raw_image = struct.pack(">H", 0) + b"\x00" * (3 * width * height)
    return header + color_mode + resource_section + layer_mask + raw_image


def _write_zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ((0o40755 if name.endswith("/") else 0o100644) << 16)
    archive.writestr(info, data)


def generate_fixture_tree(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for child in destination.iterdir():
        if child.name == "README.md":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    png = _synthetic_image((40, 30), (110, 40, 160), "TEST-ASSET")
    png.save(destination / "synthetic.png", format="PNG")
    png.close()

    jpeg = _synthetic_image((36, 28), (20, 130, 90), "SYNTHETIC-002")
    jpeg.save(destination / "synthetic.jpg", format="JPEG", quality=85)
    jpeg.close()

    gif = _synthetic_image((24, 24), (180, 80, 20), "T")
    gif.save(destination / "synthetic.gif", format="GIF")
    gif.close()

    with zipfile.ZipFile(destination / "synthetic.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        _write_zip_entry(archive, "docs/readme.txt", b"SYNTHETIC ZIP\n")
        _write_zip_entry(archive, "data/item-001.txt", b"alpha\n")
        _write_zip_entry(archive, "data/item-002.txt", b"beta\n")
        _write_zip_entry(archive, "empty/", b"")
    (destination / "corrupt.zip").write_bytes(b"PK\x03\x04CORRUPT-SYNTHETIC")

    thumbnail, _, _ = _jpeg_bytes()
    (destination / "minimal.psd").write_bytes(_psd_bytes())
    (destination / "thumbnail.psd").write_bytes(_psd_bytes(thumbnail))
    (destination / "truncated.psd").write_bytes(_psd_bytes()[:18])

    duplicate_payload = b"SYNTHETIC-DUPLICATE\n" * 8
    (destination / "duplicate-a.bin").write_bytes(duplicate_payload)
    (destination / "duplicate-b.bin").write_bytes(duplicate_payload)
    (destination / "same-size-a.bin").write_bytes(b"A" * 64)
    (destination / "same-size-b.bin").write_bytes(b"B" * 64)
    (destination / "unicode_测试.txt").write_text("UNICODE-SYNTHETIC\n", encoding="utf-8")

    deep = destination / "level-01" / "level-02" / "level-03"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_text("DEEP-SYNTHETIC\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destination",
        nargs="?",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "synthetic",
    )
    args = parser.parse_args()
    generate_fixture_tree(args.destination)
    print("synthetic fixtures generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

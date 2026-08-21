"""Safe preview export and contact-sheet generation."""

from __future__ import annotations

from io import BytesIO
import hashlib
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError


SUPPORTED_PREVIEW_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif"}


def write_jpeg_preview(output_dir: Path, relative_path: str, jpeg: bytes, resource_id: int) -> dict:
    try:
        with Image.open(BytesIO(jpeg)) as image:
            if image.format != "JPEG":
                raise ValueError("embedded preview is not JPEG")
            image.verify()
    except (OSError, ValueError, UnidentifiedImageError) as error:
        raise ValueError("embedded preview failed image validation") from error

    digest = hashlib.sha256(relative_path.encode("utf-8") + b"\x00" + jpeg).hexdigest()[:24]
    preview_dir = output_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"{digest}.jpg"
    preview_path.write_bytes(jpeg)
    return {
        "relative_path": relative_path,
        "preview_path": preview_path.relative_to(output_dir).as_posix(),
        "resource_id": resource_id,
    }


def create_contact_sheet(
    preview_dir: Path,
    output_file: Path,
    columns: int = 4,
    cell_size: tuple[int, int] = (180, 180),
) -> int:
    if columns < 1:
        raise ValueError("columns must be positive")
    candidates = sorted(
        (
            path
            for path in preview_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_PREVIEW_SUFFIXES
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    opened: list[Image.Image] = []
    for path in candidates:
        try:
            with Image.open(path) as source:
                opened.append(source.convert("RGB"))
        except (OSError, UnidentifiedImageError):
            continue
    if not opened:
        raise ValueError("preview directory contains no readable images")

    label_height = 24
    rows = math.ceil(len(opened) / columns)
    sheet = Image.new(
        "RGB",
        (columns * cell_size[0], rows * (cell_size[1] + label_height)),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, source in enumerate(opened, start=1):
        column = (index - 1) % columns
        row = (index - 1) // columns
        contained = ImageOps.contain(source, cell_size, Image.Resampling.LANCZOS)
        x = column * cell_size[0] + (cell_size[0] - contained.width) // 2
        y = row * (cell_size[1] + label_height) + (cell_size[1] - contained.height) // 2
        sheet.paste(contained, (x, y))
        draw.text(
            (column * cell_size[0] + 8, row * (cell_size[1] + label_height) + cell_size[1] + 4),
            f"{index:03d}",
            fill="black",
        )
        contained.close()
        source.close()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    image_format = "JPEG" if output_file.suffix.lower() in {".jpg", ".jpeg"} else "PNG"
    sheet.save(output_file, format=image_format)
    sheet.close()
    return len(opened)

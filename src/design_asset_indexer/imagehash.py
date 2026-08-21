"""Minimal 64-bit difference hash helpers."""

from __future__ import annotations

from PIL import Image


def dhash64(image: Image.Image) -> int:
    grayscale = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = grayscale.load()
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(pixels[column, row] > pixels[column + 1, row])
    return value


def hamming_distance(left: int, right: int) -> int:
    if left < 0 or right < 0 or left.bit_length() > 64 or right.bit_length() > 64:
        raise ValueError("dHash values must be unsigned 64-bit integers")
    return (left ^ right).bit_count()

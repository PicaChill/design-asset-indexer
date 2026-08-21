from pathlib import Path

import pytest

from design_asset_indexer.detect import detect_bytes, detect_file


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"8BPS\x00\x01", "PSD"),
        (b"8BPS\x00\x02", "PSB"),
        (b"\xff\xd8\xff\xe0", "JPEG"),
        (b"\x89PNG\r\n\x1a\n", "PNG"),
        (b"GIF89a", "GIF"),
        (b"PK\x03\x04", "ZIP"),
        (b"not-a-known-signature", "OTHER"),
    ],
)
def test_magic_detection(header: bytes, expected: str) -> None:
    assert detect_bytes(header) == expected


def test_detection_ignores_misleading_suffix(tmp_path: Path) -> None:
    path = tmp_path / "misleading.png"
    path.write_bytes(b"GIF89a" + b"\x00" * 32)
    assert detect_file(path) == "GIF"

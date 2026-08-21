from pathlib import Path

from PIL import Image
import pytest

from design_asset_indexer.imagehash import dhash64, hamming_distance
from design_asset_indexer.previews import create_contact_sheet


def test_dhash_and_hamming_distance() -> None:
    left = Image.new("L", (64, 64))
    left.putdata([column * 4 for _row in range(64) for column in range(64)])
    right = left.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    left_hash = dhash64(left)
    right_hash = dhash64(right)
    assert hamming_distance(left_hash, left_hash) == 0
    assert hamming_distance(left_hash, right_hash) > 0


def test_contact_sheet_uses_sequence_labels_only(tmp_path: Path) -> None:
    preview_dir = tmp_path / "previews"
    preview_dir.mkdir()
    Image.new("RGB", (20, 30), "red").save(preview_dir / "private-looking-name.jpg")
    Image.new("RGB", (40, 15), "blue").save(preview_dir / "another-name.png")
    output = tmp_path / "sheet.jpg"
    assert create_contact_sheet(preview_dir, output, columns=2) == 2
    assert output.is_file()
    with Image.open(output) as sheet:
        assert sheet.width == 360


def test_contact_sheet_rejects_empty_directory(tmp_path: Path) -> None:
    preview_dir = tmp_path / "empty"
    preview_dir.mkdir()
    with pytest.raises(ValueError, match="no readable images"):
        create_contact_sheet(preview_dir, tmp_path / "sheet.png")

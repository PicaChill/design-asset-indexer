from pathlib import Path

import pytest

from design_asset_indexer.psd import PSDParseError, parse_psd


def test_psd_header_parser(fixture_tree: Path) -> None:
    metadata = parse_psd(fixture_tree / "minimal.psd")
    assert metadata.signature == "8BPS"
    assert metadata.version == 1
    assert (metadata.width, metadata.height) == (16, 12)
    assert metadata.channels == 3
    assert metadata.depth == 8
    assert metadata.color_mode == 3


def test_psd_thumbnail_resource(fixture_tree: Path) -> None:
    metadata = parse_psd(fixture_tree / "thumbnail.psd")
    assert metadata.thumbnail_resource_id == 1036
    assert metadata.thumbnail_jpeg is not None
    assert metadata.thumbnail_jpeg.startswith(b"\xff\xd8\xff")


def test_truncated_psd_is_structured_error(fixture_tree: Path) -> None:
    with pytest.raises(PSDParseError, match="truncated"):
        parse_psd(fixture_tree / "truncated.psd")

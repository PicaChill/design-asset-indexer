from pathlib import Path

from design_asset_indexer import archive
from design_asset_indexer import duplicates


def test_zip_index_lists_without_extraction(fixture_tree: Path) -> None:
    record = archive.index_zip(fixture_tree / "synthetic.zip", "synthetic.zip")
    assert record["error"] is None
    assert record["entry_count"] == 4
    assert record["entries"][0]["name"] == "data/item-001.txt"
    assert not (fixture_tree / "docs" / "readme.txt").exists()


def test_corrupt_zip_records_error(fixture_tree: Path) -> None:
    record = archive.index_zip(fixture_tree / "corrupt.zip", "corrupt.zip")
    assert record["error"] == "BadZipFile"
    assert record["entries"] == []


def test_zip_entry_safety_limit_precedes_zipfile_open(fixture_tree: Path, monkeypatch) -> None:
    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("ZipFile must not open an archive rejected by preflight")

    monkeypatch.setattr(archive.zipfile, "ZipFile", forbidden_open)
    record = archive.index_zip(fixture_tree / "synthetic.zip", "synthetic.zip", max_entries=2)
    assert record["error"] == "ValueError"


def test_duplicate_prefilter_and_exact_hash(tmp_path: Path, monkeypatch) -> None:
    unique = tmp_path / "unique.bin"
    left = tmp_path / "left.bin"
    right = tmp_path / "right.bin"
    unique.write_bytes(b"x")
    left.write_bytes(b"same")
    right.write_bytes(b"same")
    calls: list[str] = []
    original = duplicates.sha256_file

    def tracked(path: Path, chunk_size: int = duplicates.CHUNK_SIZE) -> str:
        calls.append(path.name)
        return original(path, chunk_size)

    monkeypatch.setattr(duplicates, "sha256_file", tracked)
    result = duplicates.find_duplicate_candidates(
        [(item.name, item, item.stat().st_size) for item in (unique, left, right)]
    )
    assert calls == ["left.bin", "right.bin"]
    assert result["groups"][0]["paths"] == ["left.bin", "right.bin"]


def test_same_size_different_content_is_not_duplicate(fixture_tree: Path) -> None:
    paths = [fixture_tree / "same-size-a.bin", fixture_tree / "same-size-b.bin"]
    result = duplicates.find_duplicate_candidates(
        [(path.name, path, path.stat().st_size) for path in paths]
    )
    assert result["groups"] == []

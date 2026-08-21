from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from design_asset_indexer.inventory import scan_directory


def _snapshot(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_inventory_outputs_stable_relative_paths_and_unicode(fixture_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "output"
    summary = scan_directory(fixture_tree, output)
    rows = _jsonl(output / "inventory.jsonl")
    relative_paths = [row["relative_path"] for row in rows]
    assert relative_paths == sorted(relative_paths, key=lambda value: (value.casefold(), value))
    assert "unicode_测试.txt" in relative_paths
    assert all(not Path(value).is_absolute() for value in relative_paths)
    assert summary["file_count"] == len(rows)
    for name in (
        "inventory.csv",
        "inventory.jsonl",
        "archives.jsonl",
        "duplicates.json",
        "previews.jsonl",
        "summary.json",
    ):
        assert (output / name).is_file()


def test_scan_does_not_mutate_input_or_extract_zip(fixture_tree: Path, tmp_path: Path) -> None:
    before = _snapshot(fixture_tree)
    scan_directory(fixture_tree, tmp_path / "output")
    after = _snapshot(fixture_tree)
    assert before == after
    assert not (fixture_tree / "docs" / "readme.txt").exists()


def test_scan_records_corrupt_files_without_stopping(fixture_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "output"
    summary = scan_directory(fixture_tree, output)
    rows = {row["relative_path"]: row for row in _jsonl(output / "inventory.jsonl")}
    assert rows["corrupt.zip"]["error"] == "BadZipFile"
    assert rows["truncated.psd"]["error"] == "PSDParseError"
    assert summary["error_count"] >= 2


def test_embedded_preview_uses_safe_name_and_mapping(fixture_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "output"
    scan_directory(fixture_tree, output)
    mappings = _jsonl(output / "previews.jsonl")
    assert len(mappings) == 1
    mapping = mappings[0]
    preview_name = Path(mapping["preview_path"]).name
    assert mapping["relative_path"] == "thumbnail.psd"
    assert preview_name.endswith(".jpg")
    assert "thumbnail" not in preview_name
    assert (output / mapping["preview_path"]).is_file()


def test_output_inside_input_is_rejected(fixture_tree: Path) -> None:
    with pytest.raises(ValueError, match="must not be inside"):
        scan_directory(fixture_tree, fixture_tree / "output")


def test_reports_do_not_contain_absolute_input_path(fixture_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "output"
    scan_directory(fixture_tree, output)
    source_text = str(fixture_tree.resolve())
    for report in output.glob("*.*"):
        if report.suffix in {".csv", ".json", ".jsonl"}:
            assert source_text not in report.read_text(encoding="utf-8")

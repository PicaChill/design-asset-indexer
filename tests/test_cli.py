from pathlib import Path

from design_asset_indexer.cli import main


def test_cli_scan_success(fixture_tree: Path, tmp_path: Path, capsys) -> None:
    result = main(["scan", str(fixture_tree), "--out", str(tmp_path / "output")])
    captured = capsys.readouterr()
    assert result == 0
    assert '"file_count"' in captured.out
    assert captured.err == ""


def test_cli_malformed_input_returns_two(tmp_path: Path, capsys) -> None:
    result = main(["scan", str(tmp_path / "missing"), "--out", str(tmp_path / "output")])
    captured = capsys.readouterr()
    assert result == 2
    assert "input directory is unavailable" in captured.err
    assert str(tmp_path) not in captured.err


def test_cli_contact_sheet_success(fixture_tree: Path, tmp_path: Path) -> None:
    output = tmp_path / "sheet.png"
    result = main(["contact-sheet", str(fixture_tree), "--out", str(output), "--columns", "3"])
    assert result == 0
    assert output.is_file()

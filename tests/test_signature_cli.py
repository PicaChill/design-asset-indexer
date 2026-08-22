from __future__ import annotations

import json
from pathlib import Path

from design_asset_indexer import cli
from design_asset_indexer.photoshop import ReplaceResult, TextLayerInfo


def _make_psd(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"8BPS\x00\x01SYNTHETIC")


class AvailableAdapter:
    instance: "AvailableAdapter | None" = None

    def __init__(self) -> None:
        type(self).instance = self
        self.replace_calls: list[Path] = []

    def is_available(self) -> bool:
        return True

    def inspect_text_layers(self, path: Path) -> list[TextLayerInfo]:
        return [TextLayerInfo("Signature", "Signature", "TEXT", "OLD")]

    def replace_exact_text(
        self,
        path: Path,
        old_text: str,
        new_text: str,
        layer_name: str | None = None,
    ) -> ReplaceResult:
        self.replace_calls.append(path)
        return ReplaceResult(1, 1)


class UnavailableAdapter:
    def is_available(self) -> bool:
        return False


def test_signature_inspect_cli_writes_structured_reports(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "input"
    _make_psd(source / "one.psd")
    output = tmp_path / "reports"
    monkeypatch.setattr(cli, "PhotoshopAdapter", AvailableAdapter)

    result = cli.main(
        [
            "signature-inspect",
            str(source),
            "--out",
            str(output),
            "--layer-name",
            "Signature",
            "--contains-text",
            "OLD",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert json.loads(captured.out)["matched_layer_count"] == 1
    assert captured.err == ""
    assert (output / "signature_layers.csv").is_file()


def test_signature_replace_cli_dry_run_never_creates_psd(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "input"
    _make_psd(source / "one.psd")
    output = tmp_path / "output"
    monkeypatch.setattr(cli, "PhotoshopAdapter", AvailableAdapter)

    result = cli.main(
        [
            "signature-replace",
            str(source),
            "--out",
            str(output),
            "--from",
            "OLD",
            "--to",
            "NEW",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()

    assert result == 0
    assert json.loads(captured.out)["status_counts"] == {"WOULD_REPLACE": 1}
    assert captured.err == ""
    assert not (output / "one.psd").exists()
    assert AvailableAdapter.instance is not None
    assert AvailableAdapter.instance.replace_calls == []


def test_signature_cli_reports_unavailable_photoshop_without_host_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "private-input"
    _make_psd(source / "one.psd")
    monkeypatch.setattr(cli, "PhotoshopAdapter", UnavailableAdapter)

    result = cli.main(
        ["signature-inspect", str(source), "--out", str(tmp_path / "reports")]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert "Adobe Photoshop automation is unavailable" in captured.err
    assert str(tmp_path) not in captured.err


def test_signature_replace_cli_rejects_empty_replacement(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "input"
    _make_psd(source / "one.psd")
    monkeypatch.setattr(cli, "PhotoshopAdapter", AvailableAdapter)

    result = cli.main(
        [
            "signature-replace",
            str(source),
            "--out",
            str(tmp_path / "output"),
            "--from",
            "OLD",
            "--to",
            "",
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert "replacement text must not be empty" in captured.err

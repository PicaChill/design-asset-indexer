from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from design_asset_indexer.photoshop import (
    PhotoshopAdapter,
    PhotoshopOpenError,
    PhotoshopSaveError,
    ReplaceResult,
    TextLayerInfo,
)
from design_asset_indexer.signatures import inspect_signatures, replace_signatures


def _layer(name: str, text: str, path: str | None = None) -> TextLayerInfo:
    return TextLayerInfo(path or name, name, "TEXT", text)


def _make_psd(root: Path, relative: str, payload: bytes = b"SOURCE") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"8BPS\x00\x01" + payload)
    return path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class FakeAdapter:
    def __init__(
        self,
        layers: dict[str, list[TextLayerInfo]] | None = None,
        inspect_errors: dict[str, Exception] | None = None,
        replace_results: dict[str, ReplaceResult | Exception] | None = None,
    ) -> None:
        self.layers = layers or {}
        self.inspect_errors = inspect_errors or {}
        self.replace_results = replace_results or {}
        self.inspect_calls: list[Path] = []
        self.replace_calls: list[tuple[Path, str, str, str | None]] = []

    def inspect_text_layers(self, path: Path) -> list[TextLayerInfo]:
        self.inspect_calls.append(path)
        if path.name in self.inspect_errors:
            raise self.inspect_errors[path.name]
        return list(self.layers.get(path.name, []))

    def replace_exact_text(
        self,
        path: Path,
        old_text: str,
        new_text: str,
        layer_name: str | None = None,
    ) -> ReplaceResult:
        self.replace_calls.append((path, old_text, new_text, layer_name))
        result = self.replace_results.get(path.name, ReplaceResult(1, 1))
        if isinstance(result, Exception):
            raise result
        return result


def test_inspect_writes_required_reports_and_applies_filters(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    adapter = FakeAdapter(
        {
            "one.psd": [
                _layer("Signature", "old signature", "Group / Signature"),
                _layer("Caption", "caption"),
            ]
        }
    )
    output = tmp_path / "reports"

    summary = inspect_signatures(
        source,
        output,
        adapter,
        layer_name="Signature",
        contains_text="signature",
    )

    assert summary == {
        "command": "signature-inspect",
        "file_count": 1,
        "document_opened_count": 1,
        "layer_count": 2,
        "matched_layer_count": 1,
        "error_count": 0,
        "max_files_reached": False,
    }
    rows = _read_jsonl(output / "signature_layers.jsonl")
    assert [row["matched"] for row in rows] == [True, False]
    assert rows[0]["layer_path"] == "Group / Signature"
    assert (output / "signature_layers.csv").is_file()
    assert json.loads((output / "summary.json").read_text(encoding="utf-8")) == summary


def test_inspect_records_open_failure_and_empty_document(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "broken.psd")
    _make_psd(source, "empty.psd")
    adapter = FakeAdapter(
        inspect_errors={
            "broken.psd": PhotoshopOpenError("Photoshop could not open a PSD")
        }
    )

    summary = inspect_signatures(source, tmp_path / "reports", adapter)
    rows = _read_jsonl(tmp_path / "reports" / "signature_layers.jsonl")

    assert summary["file_count"] == 2
    assert summary["error_count"] == 1
    assert rows[0]["document_opened"] is False
    assert rows[0]["error"] == "PHOTOSHOP_OPEN_FAILED"
    assert rows[1]["document_opened"] is True
    assert rows[1]["layer_name"] == ""


def test_recursive_include_and_limit_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "b.psd")
    _make_psd(source, "nested/a.psd")
    _make_psd(source, "nested/c.psd")
    _make_psd(source, "ignored.PSB")
    adapter = FakeAdapter()

    summary = inspect_signatures(
        source,
        tmp_path / "reports",
        adapter,
        recursive=True,
        include="*.psd",
        max_files=2,
    )

    assert summary["file_count"] == 2
    assert summary["max_files_reached"] is True
    assert [path.relative_to(source).as_posix() for path in adapter.inspect_calls] == [
        "b.psd",
        "nested/a.psd",
    ]


def test_photoshop_layer_walk_reports_multilevel_group_path() -> None:
    class WalkAdapter(PhotoshopAdapter):
        @classmethod
        def _items(cls, collection):
            yield from collection

    text_layer = SimpleNamespace(
        Name="Text Layer",
        typename="ArtLayer",
        Kind=2,
        TextItem=SimpleNamespace(Contents="署名"),
    )
    nested_group = SimpleNamespace(
        Name="Nested",
        typename="LayerSet",
        Layers=[text_layer],
    )
    outer_group = SimpleNamespace(
        Name="Group A",
        typename="LayerSet",
        Layers=[nested_group],
    )

    layers = list(WalkAdapter()._walk_text_layers([outer_group]))

    assert layers[0][0].layer_path == "Group A / Nested / Text Layer"
    assert layers[0][0].current_text == "署名"


def test_single_match_replaces_only_copied_output_and_preserves_source(tmp_path: Path) -> None:
    source_root = tmp_path / "input"
    source = _make_psd(source_root, "nested/one.psd", b"ORIGINAL")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    adapter = FakeAdapter({"one.psd": [_layer("Signature", "OLD")]})
    output = tmp_path / "output"

    summary = replace_signatures(
        source_root,
        output,
        adapter,
        old_text="OLD",
        new_text="NEW",
        recursive=True,
    )

    assert summary["status_counts"] == {"REPLACED": 1}
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert (output / "nested" / "one.psd").read_bytes() == source.read_bytes()
    assert adapter.replace_calls == [
        (output / "nested" / "one.psd", "OLD", "NEW", None)
    ]
    row = _read_jsonl(output / "signature_replace_results.jsonl")[0]
    assert row["status"] == "REPLACED"
    assert row["changed_layer_count"] == 1


def test_zero_and_multiple_matches_are_skipped(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "none.psd")
    _make_psd(source, "many.psd")
    adapter = FakeAdapter(
        {
            "none.psd": [_layer("Caption", "OTHER")],
            "many.psd": [_layer("A", "OLD"), _layer("B", "OLD")],
        }
    )
    output = tmp_path / "output"

    summary = replace_signatures(
        source,
        output,
        adapter,
        old_text="OLD",
        new_text="NEW",
    )

    assert summary["status_counts"] == {
        "SKIPPED_AMBIGUOUS": 1,
        "SKIPPED_NO_MATCH": 1,
    }
    assert not (output / "none.psd").exists()
    assert not (output / "many.psd").exists()
    assert adapter.replace_calls == []


def test_layer_name_can_resolve_text_ambiguity(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    adapter = FakeAdapter(
        {"one.psd": [_layer("Target", "OLD"), _layer("Other", "OLD")]}
    )

    summary = replace_signatures(
        source,
        tmp_path / "output",
        adapter,
        old_text="OLD",
        new_text="NEW",
        layer_name="Target",
    )

    assert summary["status_counts"] == {"REPLACED": 1}
    assert adapter.replace_calls[0][3] == "Target"


def test_dry_run_writes_plan_without_psd_or_replace_call(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "replace.psd")
    _make_psd(source, "skip.psd")
    adapter = FakeAdapter(
        {
            "replace.psd": [_layer("Signature", "OLD")],
            "skip.psd": [_layer("Signature", "OTHER")],
        }
    )
    output = tmp_path / "output"

    summary = replace_signatures(
        source,
        output,
        adapter,
        old_text="OLD",
        new_text="NEW",
        dry_run=True,
    )

    decisions = {row["relative_path"]: row["decision"] for row in _read_jsonl(output / "planned_changes.jsonl")}
    assert decisions == {"replace.psd": "WOULD_REPLACE", "skip.psd": "SKIP_NO_MATCH"}
    assert summary["changed_layer_count"] == 0
    assert not (output / "replace.psd").exists()
    assert adapter.replace_calls == []
    assert (output / "planned_changes.csv").is_file()
    assert (output / "summary.json").is_file()


def test_dry_run_maps_photoshop_failure_to_error_decision(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "broken.psd")
    adapter = FakeAdapter(
        inspect_errors={
            "broken.psd": PhotoshopOpenError("Photoshop could not open a PSD")
        }
    )

    replace_signatures(
        source,
        tmp_path / "output",
        adapter,
        old_text="OLD",
        new_text="NEW",
        dry_run=True,
    )

    row = _read_jsonl(tmp_path / "output" / "planned_changes.jsonl")[0]
    assert row["decision"] == "ERROR"
    assert row["error_code"] == "PHOTOSHOP_OPEN_FAILED"


def test_existing_output_is_skipped_without_opening_source(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    _make_psd(output, "one.psd", b"EXISTING")
    adapter = FakeAdapter({"one.psd": [_layer("Signature", "OLD")]})

    summary = replace_signatures(
        source,
        output,
        adapter,
        old_text="OLD",
        new_text="NEW",
        dry_run=True,
    )

    assert summary["status_counts"] == {"SKIPPED_EXISTS": 1}
    assert _read_jsonl(output / "planned_changes.jsonl")[0]["decision"] == "SKIP_EXISTS"
    assert adapter.inspect_calls == []
    assert adapter.replace_calls == []


@pytest.mark.parametrize("layout", ["same", "output_inside", "input_inside"])
def test_overlapping_roots_are_rejected_before_writes(tmp_path: Path, layout: str) -> None:
    if layout == "same":
        source = tmp_path / "input"
        source.mkdir()
        output = source
    elif layout == "output_inside":
        source = tmp_path / "input"
        source.mkdir()
        output = source / "output"
    else:
        output = tmp_path / "container"
        source = output / "input"
        source.mkdir(parents=True)

    with pytest.raises(ValueError, match="must not overlap"):
        replace_signatures(
            source,
            output,
            FakeAdapter(),
            old_text="OLD",
            new_text="NEW",
        )


@pytest.mark.parametrize(
    ("old_text", "new_text", "message"),
    [
        ("", "NEW", "source text must not be empty"),
        ("OLD", "", "replacement text must not be empty"),
        ("SAME", "SAME", "must differ"),
    ],
)
def test_empty_and_noop_replacements_are_rejected(
    tmp_path: Path,
    old_text: str,
    new_text: str,
    message: str,
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    with pytest.raises(ValueError, match=message):
        replace_signatures(
            source,
            tmp_path / "output",
            FakeAdapter(),
            old_text=old_text,
            new_text=new_text,
        )


def test_unicode_and_multiline_text_are_passed_without_rewriting(tmp_path: Path) -> None:
    source = tmp_path / "中文输入"
    _make_psd(source, "分组/表情署名.psd")
    old_text = "旧署名\n第二行"
    new_text = "新署名 ✅\n第二行"
    adapter = FakeAdapter({"表情署名.psd": [_layer("署名", old_text)]})

    replace_signatures(
        source,
        tmp_path / "中文输出",
        adapter,
        old_text=old_text,
        new_text=new_text,
        recursive=True,
    )

    assert adapter.replace_calls[0][0].name == "表情署名.psd"
    assert adapter.replace_calls[0][1:3] == (old_text, new_text)


def test_save_failure_is_reported_and_batch_continues(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        replace_results={
            "a.psd": PhotoshopSaveError("Photoshop could not save the output copy")
        },
    )

    summary = replace_signatures(
        source,
        tmp_path / "output",
        adapter,
        old_text="OLD",
        new_text="NEW",
    )

    assert summary["status_counts"] == {"FAILED_SAVE": 1, "REPLACED": 1}
    rows = _read_jsonl(tmp_path / "output" / "signature_replace_results.jsonl")
    assert rows[0]["error_code"] == "PHOTOSHOP_SAVE_FAILED"
    assert rows[1]["status"] == "REPLACED"


def test_non_psd_magic_is_not_sent_to_photoshop(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    (source / "fake.psd").write_bytes(b"not a real PSD")
    adapter = FakeAdapter()

    summary = inspect_signatures(source, tmp_path / "reports", adapter)

    assert summary["file_count"] == 0
    assert adapter.inspect_calls == []

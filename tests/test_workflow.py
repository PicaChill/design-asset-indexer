from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
import json
from pathlib import Path
from typing import Callable

import pytest

from design_asset_indexer.photoshop import (
    PhotoshopOpenError,
    ReplaceResult,
    TextLayerInfo,
)
from design_asset_indexer.workflow import (
    build_public_diagnostic,
    create_signature_execution_plan,
    execute_signature_plan,
    inspect_signature_workflow,
    validate_execution_plan,
)
from design_asset_indexer.workflow_models import (
    CancellationToken,
    PlanValidationStatus,
    SignatureRule,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowOptions,
)


def _make_psd(root: Path, relative: str, payload: bytes = b"SOURCE") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"8BPS\x00\x01" + payload)
    return path


def _layer(name: str, text: str, path: str | None = None) -> TextLayerInfo:
    return TextLayerInfo(path or name, name, "TEXT", text)


class FakeAdapter:
    def __init__(
        self,
        layers: dict[str, list[TextLayerInfo]] | None = None,
        *,
        inspect_errors: dict[str, Exception] | None = None,
        on_replace: Callable[[Path], None] | None = None,
    ) -> None:
        self.layers = layers or {}
        self.inspect_errors = inspect_errors or {}
        self.on_replace = on_replace
        self.inspect_calls: list[Path] = []
        self.replace_calls: list[Path] = []

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
        self.replace_calls.append(path)
        if self.on_replace is not None:
            self.on_replace(path)
        return ReplaceResult(1, 1)


def _options(source: Path, output: Path, **changes) -> WorkflowOptions:
    values = {
        "input_dir": source,
        "output_dir": output,
        "recursive": False,
        "include": "*.psd",
        "max_files": 100,
    }
    values.update(changes)
    return WorkflowOptions(**values)


def _rule(**changes) -> SignatureRule:
    values = {"old_text": "OLD", "new_text": "NEW", "layer_name": None}
    values.update(changes)
    return SignatureRule(**values)


def _matching_adapter(*names: str) -> FakeAdapter:
    return FakeAdapter({name: [_layer("Signature", "OLD")] for name in names})


def test_plan_is_frozen(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"),
        _rule(),
        _matching_adapter("one.psd"),
    )

    with pytest.raises(FrozenInstanceError):
        plan.plan_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.rule.old_text = "changed"  # type: ignore[misc]
    assert isinstance(plan.items, tuple)
    assert isinstance(plan.source_snapshot, tuple)


def test_same_input_produces_same_plan_id(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    options = _options(source, tmp_path / "output")

    first = create_signature_execution_plan(
        options, _rule(), _matching_adapter("one.psd")
    )
    second = create_signature_execution_plan(
        options, _rule(), _matching_adapter("one.psd")
    )

    assert first.plan_id == second.plan_id


def test_rule_change_changes_plan_id(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    options = _options(source, tmp_path / "output")

    first = create_signature_execution_plan(
        options, _rule(), _matching_adapter("one.psd")
    )
    second = create_signature_execution_plan(
        options,
        _rule(new_text="DIFFERENT"),
        _matching_adapter("one.psd"),
    )

    assert first.plan_id != second.plan_id


def test_recursive_change_changes_plan_id(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "top.psd")
    _make_psd(source, "nested/child.psd")
    output = tmp_path / "output"

    shallow = create_signature_execution_plan(
        _options(source, output),
        _rule(),
        _matching_adapter("top.psd", "child.psd"),
    )
    recursive = create_signature_execution_plan(
        _options(source, output, recursive=True),
        _rule(),
        _matching_adapter("top.psd", "child.psd"),
    )

    assert shallow.plan_id != recursive.plan_id


def test_include_change_changes_plan_id(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    output = tmp_path / "output"

    all_files = create_signature_execution_plan(
        _options(source, output),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )
    only_a = create_signature_execution_plan(
        _options(source, output, include="a*.psd"),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )

    assert all_files.plan_id != only_a.plan_id


def test_max_files_change_changes_plan_id(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    output = tmp_path / "output"

    one = create_signature_execution_plan(
        _options(source, output, max_files=1),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )
    two = create_signature_execution_plan(
        _options(source, output, max_files=2),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )

    assert one.plan_id != two.plan_id


def test_source_added_invalidates_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"),
        _rule(),
        _matching_adapter("a.psd"),
    )

    _make_psd(source, "b.psd")

    assert validate_execution_plan(plan).status is PlanValidationStatus.STALE_SOURCE_SET


def test_source_removed_invalidates_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    path = _make_psd(source, "one.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"),
        _rule(),
        _matching_adapter("one.psd"),
    )

    path.unlink()

    assert validate_execution_plan(plan).status is PlanValidationStatus.STALE_SOURCE_SET


def test_source_stat_change_invalidates_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    path = _make_psd(source, "one.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"),
        _rule(),
        _matching_adapter("one.psd"),
    )

    path.write_bytes(path.read_bytes() + b"CHANGED")

    validation = validate_execution_plan(plan)
    assert validation.status is PlanValidationStatus.STALE_SOURCE_FILE
    assert validation.relative_path == "one.psd"


def test_output_created_after_dry_run_blocks_execution(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)
    appeared = _make_psd(output, "one.psd", b"EXTERNAL")
    before = appeared.read_bytes()

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.processed_count == 0
    assert result.workflow_status == "EXECUTION_STOPPED_PLAN_STALE"
    assert adapter.replace_calls == []
    assert appeared.read_bytes() == before
    assert not (output / "signature_replace_results.csv").exists()


def test_max_files_reached_preserved_in_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")

    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output", max_files=1),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )

    assert plan.max_files_reached is True
    assert len(plan.items) == 1
    assert plan.candidate_relative_paths == ("a.psd", "b.psd")


def test_plan_no_match_matches_v020_semantics(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    adapter = FakeAdapter({"one.psd": [_layer("Signature", "OTHER")]})

    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"), _rule(), adapter
    )

    assert plan.items[0].decision == "SKIP_NO_MATCH"
    assert plan.items[0].matched_layer_count == 0


def test_plan_ambiguous_matches_v020_semantics(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    adapter = FakeAdapter(
        {"one.psd": [_layer("A", "OLD"), _layer("B", "OLD")]}
    )

    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"), _rule(), adapter
    )

    assert plan.items[0].decision == "SKIP_AMBIGUOUS"
    assert plan.items[0].matched_layer_count == 2


def test_plan_existing_output_matches_v020_semantics(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    _make_psd(output, "one.psd", b"EXISTING")
    adapter = _matching_adapter("one.psd")

    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    assert plan.items[0].decision == "SKIP_EXISTS"
    assert adapter.inspect_calls == []


def test_plan_would_replace_matches_v020_semantics(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")

    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"),
        _rule(layer_name="Signature"),
        _matching_adapter("one.psd"),
    )

    assert plan.items[0].decision == "WOULD_REPLACE"
    assert plan.items[0].matched_layer_count == 1


def test_execute_uses_plan_without_new_parameters(tmp_path: Path) -> None:
    signature = inspect.signature(execute_signature_plan)

    assert "old_text" not in signature.parameters
    assert "new_text" not in signature.parameters
    assert "output_dir" not in signature.parameters

    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"), _rule(), adapter
    )
    with pytest.raises(TypeError):
        execute_signature_plan(plan, adapter, old_text="OTHER")  # type: ignore[call-arg]


def test_execute_plan_creates_only_confirmed_outputs(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "replace.psd")
    _make_psd(source, "skip.psd")
    output = tmp_path / "output"
    adapter = FakeAdapter(
        {
            "replace.psd": [_layer("Signature", "OLD")],
            "skip.psd": [_layer("Signature", "OTHER")],
        }
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter)

    assert result.complete is True
    assert (output / "replace.psd").is_file()
    assert not (output / "skip.psd").exists()
    assert [item.status for item in result.items] == ["REPLACED", "SKIPPED_NO_MATCH"]


def test_midrun_source_change_stops_before_next_mutation(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    second = _make_psd(source, "b.psd")
    output = tmp_path / "output"

    def change_second(path: Path) -> None:
        if path.name == "a.psd":
            second.write_bytes(second.read_bytes() + b"CHANGED")

    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        on_replace=change_second,
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.cancelled is False
    assert result.processed_count == 1
    assert result.remaining_count == 1
    assert (output / "a.psd").is_file()
    assert not (output / "b.psd").exists()
    assert [path.name for path in adapter.replace_calls] == ["a.psd"]


def test_midrun_output_appearance_stops_before_next_mutation(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    output = tmp_path / "output"

    def create_second_output(path: Path) -> None:
        if path.name == "a.psd":
            _make_psd(output, "b.psd", b"EXTERNAL")

    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        on_replace=create_second_output,
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.processed_count == 1
    assert (output / "a.psd").is_file()
    assert (output / "b.psd").read_bytes().endswith(b"EXTERNAL")
    assert [path.name for path in adapter.replace_calls] == ["a.psd"]


def test_partial_result_is_not_reported_complete(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    second = _make_psd(source, "b.psd")
    output = tmp_path / "output"

    def change_second(path: Path) -> None:
        second.write_bytes(second.read_bytes() + b"STALE")

    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        on_replace=change_second,
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter)

    assert result.complete is False
    assert result.workflow_status == "EXECUTION_STOPPED_PLAN_STALE"
    assert build_public_diagnostic(result)["stale"] is True


def test_cancel_before_start_creates_no_outputs(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)
    token = CancellationToken()
    token.cancel()

    result = execute_signature_plan(plan, adapter, cancellation_token=token)

    assert result.cancelled is True
    assert result.processed_count == 0
    assert result.remaining_count == 1
    assert not (output / "one.psd").exists()
    assert adapter.replace_calls == []


def test_cancel_during_first_file_finishes_current_only(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    output = tmp_path / "output"
    token = CancellationToken()
    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        on_replace=lambda _path: token.cancel(),
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter, cancellation_token=token)

    assert result.cancelled is True
    assert result.processed_count == 1
    assert result.remaining_count == 1
    assert (output / "a.psd").is_file()
    assert not (output / "b.psd").exists()
    assert [path.name for path in adapter.replace_calls] == ["a.psd"]


def test_cancel_after_complete_does_not_relabel_complete_run(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    token = CancellationToken()
    adapter = FakeAdapter(
        {"one.psd": [_layer("Signature", "OLD")]},
        on_replace=lambda _path: token.cancel(),
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter, cancellation_token=token)

    assert result.cancelled is False
    assert result.complete is True
    assert result.workflow_status == "RESULT"


def test_event_order_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)
    events: list[WorkflowEvent] = []

    execute_signature_plan(plan, adapter, event_sink=events.append)

    assert [event.kind for event in events] == [
        WorkflowEventKind.RUN_STARTED,
        WorkflowEventKind.FILE_STARTED,
        WorkflowEventKind.FILE_RESULT,
        WorkflowEventKind.RUN_COMPLETED,
    ]


def test_events_use_relative_paths(tmp_path: Path) -> None:
    source = tmp_path / "private-root"
    _make_psd(source, "nested/one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    events: list[WorkflowEvent] = []

    create_signature_execution_plan(
        _options(source, output, recursive=True),
        _rule(),
        adapter,
        event_sink=events.append,
    )

    paths = [event.relative_path for event in events if event.relative_path]
    assert paths == ["nested/one.psd", "nested/one.psd"]
    assert all(str(source) not in path for path in paths)


def test_event_sink_failure_does_not_corrupt_business_result(tmp_path: Path) -> None:
    class FailingSink:
        def emit(self, event: WorkflowEvent) -> None:
            raise RuntimeError("UI callback failed")

    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(
        _options(source, output), _rule(), adapter, event_sink=FailingSink()
    )

    result = execute_signature_plan(plan, adapter, event_sink=FailingSink())

    assert result.complete is True
    assert (output / "one.psd").is_file()
    assert "EVENT_SINK_ERROR" in result.diagnostics


def test_public_diagnostic_redacts_absolute_paths(tmp_path: Path) -> None:
    source = tmp_path / "private-input"
    _make_psd(source, "private-name.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "private-output"),
        _rule(),
        _matching_adapter("private-name.psd"),
    )

    serialized = json.dumps(build_public_diagnostic(plan), ensure_ascii=False)

    assert str(tmp_path) not in serialized
    assert "private-name.psd" not in serialized


def test_public_diagnostic_redacts_text(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    rule = SignatureRule("PRIVATE_OLD_TEXT", "PRIVATE_NEW_TEXT", "PRIVATE_LAYER")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"),
        rule,
        FakeAdapter({"one.psd": [_layer("PRIVATE_LAYER", "PRIVATE_OLD_TEXT")]}),
    )

    serialized = json.dumps(build_public_diagnostic(plan), ensure_ascii=False)

    assert "PRIVATE_OLD_TEXT" not in serialized
    assert "PRIVATE_NEW_TEXT" not in serialized
    assert "PRIVATE_LAYER" not in serialized


def test_public_diagnostic_keeps_counts_and_error_codes(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "broken.psd")
    adapter = FakeAdapter(
        inspect_errors={
            "broken.psd": PhotoshopOpenError("Photoshop could not open a PSD")
        }
    )
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"), _rule(), adapter
    )

    diagnostic = build_public_diagnostic(plan)

    assert diagnostic["file_count"] == 1
    assert diagnostic["status_counts"] == {"ERROR": 1}
    assert diagnostic["error_codes"] == ["PHOTOSHOP_OPEN_FAILED"]


def test_inspect_workflow_returns_frozen_items_and_writes_reports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "reports"

    result = inspect_signature_workflow(
        _options(source, output),
        _matching_adapter("one.psd"),
        contains_text="OLD",
    )

    assert result.complete is True
    assert result.items[0].current_text == "OLD"
    with pytest.raises(FrozenInstanceError):
        result.items[0].current_text = "changed"  # type: ignore[misc]
    assert (output / "signature_layers.csv").is_file()
    assert (output / "signature_layers.jsonl").is_file()
    assert (output / "summary.json").is_file()


def test_validate_detects_changed_parameters_without_affecting_execute_api(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    plan = create_signature_execution_plan(
        _options(source, output), _rule(), _matching_adapter("one.psd")
    )

    validation = validate_execution_plan(
        plan,
        current_options=_options(source, output, recursive=True),
    )
    tampered = replace(plan, rule=_rule(new_text="TAMPERED"))

    assert validation.status is PlanValidationStatus.STALE_PARAMETERS
    assert validate_execution_plan(tampered).status is PlanValidationStatus.STALE_PARAMETERS


def test_workflow_reports_keep_v020_summary_schema(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)
    dry_summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))

    assert set(dry_summary) == {
        "command",
        "dry_run",
        "file_count",
        "status_counts",
        "matched_layer_count",
        "changed_layer_count",
        "max_files_reached",
    }

    execute_signature_plan(plan, adapter)
    formal_summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert set(formal_summary) == set(dry_summary)
    assert formal_summary["dry_run"] is False
    assert "cancelled" not in formal_summary
    assert "stale" not in formal_summary
    assert "plan_id" not in formal_summary

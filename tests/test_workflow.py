from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
import json
from pathlib import Path
from typing import Callable

import pytest

from design_asset_indexer.photoshop import (
    PhotoshopOpenError,
    PhotoshopReplaceError,
    ReplaceResult,
    TextLayerInfo,
)
import design_asset_indexer.workflow as workflow_module
from design_asset_indexer.workflow import (
    WorkflowPlanCancelledError,
    build_public_diagnostic,
    create_signature_execution_plan,
    execute_signature_plan,
    inspect_signature_workflow,
    plan_signature_workflow,
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
        replace_errors: dict[str, Exception] | None = None,
        on_inspect: Callable[[Path], None] | None = None,
        on_replace: Callable[[Path], None] | None = None,
    ) -> None:
        self.layers = layers or {}
        self.inspect_errors = inspect_errors or {}
        self.replace_errors = replace_errors or {}
        self.on_inspect = on_inspect
        self.on_replace = on_replace
        self.inspect_calls: list[Path] = []
        self.replace_calls: list[Path] = []

    def inspect_text_layers(self, path: Path) -> list[TextLayerInfo]:
        self.inspect_calls.append(path)
        if self.on_inspect is not None:
            self.on_inspect(path)
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
        if path.name in self.replace_errors:
            raise self.replace_errors[path.name]
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
    assert result.reports_written is False
    assert build_public_diagnostic(result)["reports_written"] is False
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
    assert result.reports_written is True
    assert build_public_diagnostic(result)["reports_written"] is True
    assert (output / "replace.psd").is_file()
    assert not (output / "skip.psd").exists()
    assert [item.status for item in result.items] == ["REPLACED", "SKIPPED_NO_MATCH"]


def test_report_write_failure_does_not_return_execution_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    def fail_report_write(*_args, **_kwargs) -> None:
        raise OSError("simulated report write failure")

    monkeypatch.setattr(
        workflow_module,
        "_write_replacement_reports",
        fail_report_write,
    )

    with pytest.raises(OSError, match="simulated report write failure"):
        execute_signature_plan(plan, adapter)


def test_execution_public_diagnostic_reports_provenance_without_private_data(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private-input"
    _make_psd(source, "private-name.psd")
    output = tmp_path / "private-output"
    rule = SignatureRule("PRIVATE_OLD_TEXT", "PRIVATE_NEW_TEXT", "PRIVATE_LAYER")
    adapter = FakeAdapter(
        {"private-name.psd": [_layer("PRIVATE_LAYER", "PRIVATE_OLD_TEXT")]}
    )
    plan = create_signature_execution_plan(_options(source, output), rule, adapter)

    result = execute_signature_plan(plan, adapter)
    diagnostic = build_public_diagnostic(result)
    serialized = json.dumps(diagnostic, ensure_ascii=False)

    assert diagnostic["reports_written"] is True
    assert str(tmp_path) not in serialized
    assert "private-name.psd" not in serialized
    assert "PRIVATE_OLD_TEXT" not in serialized
    assert "PRIVATE_NEW_TEXT" not in serialized
    assert "PRIVATE_LAYER" not in serialized


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
    assert result.reports_written is True
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


def test_plan_cancel_before_start_returns_no_executable_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    token = CancellationToken()
    token.cancel()
    events: list[WorkflowEvent] = []

    result = plan_signature_workflow(
        _options(source, output),
        _rule(),
        adapter,
        cancellation_token=token,
        event_sink=events.append,
    )

    assert result.plan is None
    assert result.cancelled is True
    assert result.processed_count == 0
    assert result.remaining_count == 1
    assert result.planned_items_complete is False
    assert result.complete is False
    assert adapter.inspect_calls == []
    assert not output.exists()
    assert events[-1].kind is WorkflowEventKind.RUN_CANCELLED


def test_plan_cancel_during_first_file_finishes_current_only(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    token = CancellationToken()
    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        on_inspect=lambda path: token.cancel() if path.name == "a.psd" else None,
    )
    events: list[WorkflowEvent] = []

    result = plan_signature_workflow(
        _options(source, tmp_path / "output"),
        _rule(),
        adapter,
        cancellation_token=token,
        event_sink=events.append,
    )

    assert result.plan is None
    assert result.cancelled is True
    assert result.processed_count == 1
    assert result.remaining_count == 1
    assert [path.name for path in adapter.inspect_calls] == ["a.psd"]
    assert events[-1].kind is WorkflowEventKind.RUN_CANCELLED


def test_plan_cancel_after_complete_returns_complete_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    token = CancellationToken()
    adapter = FakeAdapter(
        {"one.psd": [_layer("Signature", "OLD")]},
        on_inspect=lambda _path: token.cancel(),
    )
    events: list[WorkflowEvent] = []

    result = plan_signature_workflow(
        _options(source, tmp_path / "output"),
        _rule(),
        adapter,
        cancellation_token=token,
        event_sink=events.append,
    )

    assert result.plan is not None
    assert result.cancelled is False
    assert result.planned_items_complete is True
    assert result.corpus_complete is True
    assert events[-1].kind is WorkflowEventKind.RUN_COMPLETED


def test_plan_source_change_emits_terminal_stale_event(tmp_path: Path) -> None:
    source = tmp_path / "input"
    path = _make_psd(source, "one.psd")
    events: list[WorkflowEvent] = []
    adapter = FakeAdapter(
        {"one.psd": [_layer("Signature", "OLD")]},
        on_inspect=lambda _path: path.write_bytes(path.read_bytes() + b"CHANGED"),
    )

    result = plan_signature_workflow(
        _options(source, tmp_path / "output"),
        _rule(),
        adapter,
        event_sink=events.append,
    )

    assert result.plan is None
    assert result.stale is True
    assert result.cancelled is False
    assert events[-1].kind is WorkflowEventKind.RUN_STOPPED_STALE
    assert events[-1].status == PlanValidationStatus.STALE_SOURCE_FILE.value


def test_plan_output_change_emits_terminal_stale_event(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    events: list[WorkflowEvent] = []
    adapter = FakeAdapter(
        {"one.psd": [_layer("Signature", "OLD")]},
        on_inspect=lambda _path: _make_psd(output, "one.psd", b"EXTERNAL"),
    )

    result = plan_signature_workflow(
        _options(source, output),
        _rule(),
        adapter,
        event_sink=events.append,
    )

    assert result.plan is None
    assert result.stale is True
    assert events[-1].kind is WorkflowEventKind.RUN_STOPPED_STALE
    assert events[-1].status == PlanValidationStatus.STALE_OUTPUT.value
    assert not (output / "planned_changes.csv").exists()


def test_cancelled_plan_cannot_be_executed(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    adapter = _matching_adapter("one.psd")
    token = CancellationToken()
    token.cancel()
    result = plan_signature_workflow(
        _options(source, tmp_path / "output"),
        _rule(),
        adapter,
        cancellation_token=token,
    )

    with pytest.raises(TypeError, match="complete SignatureExecutionPlan"):
        execute_signature_plan(result.plan, adapter)  # type: ignore[arg-type]
    assert adapter.replace_calls == []


def test_convenience_wrapper_rejects_cancelled_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    token = CancellationToken()
    token.cancel()

    with pytest.raises(WorkflowPlanCancelledError, match="cancelled"):
        create_signature_execution_plan(
            _options(source, tmp_path / "output"),
            _rule(),
            _matching_adapter("one.psd"),
            cancellation_token=token,
        )


def test_plan_workflow_and_convenience_wrapper_share_one_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    options = _options(source, tmp_path / "output")
    adapter = _matching_adapter("one.psd")
    original = workflow_module._plan_signature_workflow_engine
    calls: list[str] = []

    def recording_engine(*args, **kwargs):
        calls.append("engine")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        workflow_module,
        "_plan_signature_workflow_engine",
        recording_engine,
    )

    workflow_result = plan_signature_workflow(options, _rule(), adapter)
    convenience_plan = create_signature_execution_plan(options, _rule(), adapter)

    assert calls == ["engine", "engine"]
    assert workflow_result.plan is not None
    assert workflow_result.plan.plan_id == convenience_plan.plan_id


def test_inspect_complete_false_when_max_files_reached(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")

    result = inspect_signature_workflow(
        _options(source, tmp_path / "reports", max_files=1),
        _matching_adapter("a.psd", "b.psd"),
    )

    assert result.planned_items_complete is True
    assert result.corpus_complete is False
    assert result.complete is False


def test_execution_complete_false_when_max_files_reached(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    adapter = _matching_adapter("a.psd", "b.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output", max_files=1),
        _rule(),
        adapter,
    )

    result = execute_signature_plan(plan, adapter)

    assert result.planned_items_complete is True
    assert result.corpus_complete is False
    assert result.complete is False


def test_planned_items_complete_true_for_finished_truncated_run(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    adapter = _matching_adapter("a.psd", "b.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output", max_files=1),
        _rule(),
        adapter,
    )

    result = execute_signature_plan(plan, adapter)

    assert result.processed_count == result.selected_count == 1
    assert result.remaining_count == 0
    assert result.planned_items_complete is True


def test_corpus_complete_false_for_finished_truncated_run(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    adapter = _matching_adapter("a.psd", "b.psd")
    result = plan_signature_workflow(
        _options(source, tmp_path / "output", max_files=1),
        _rule(),
        adapter,
    )

    assert result.planned_items_complete is True
    assert result.corpus_complete is False
    assert result.complete is False


def test_candidate_selected_unplanned_counts(tmp_path: Path) -> None:
    source = tmp_path / "input"
    for name in ("a.psd", "b.psd", "c.psd"):
        _make_psd(source, name)
    adapter = _matching_adapter("a.psd", "b.psd", "c.psd")
    result = plan_signature_workflow(
        _options(source, tmp_path / "output", max_files=2),
        _rule(),
        adapter,
    )

    assert result.candidate_count == 3
    assert result.selected_count == 2
    assert result.unplanned_count == 1
    assert result.partial_plan is True
    assert result.plan is not None
    assert result.plan.candidate_count == 3
    assert result.plan.selected_count == 2
    assert result.plan.unplanned_count == 1


def test_public_diagnostic_distinguishes_partial_plan(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output", max_files=1),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )

    diagnostic = build_public_diagnostic(plan)

    assert diagnostic["candidate_count"] == 2
    assert diagnostic["selected_count"] == 1
    assert diagnostic["unplanned_count"] == 1
    assert diagnostic["partial_plan"] is True
    assert diagnostic["planned_items_complete"] is True
    assert diagnostic["corpus_complete"] is False


def test_parent_symlink_created_after_plan_blocks_all_mutation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "nested/b.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("a.psd", "b.psd")
    plan = create_signature_execution_plan(
        _options(source, output, recursive=True), _rule(), adapter
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (output / "nested").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.processed_count == 0
    assert result.reports_written is False
    assert adapter.replace_calls == []
    assert not (output / "a.psd").exists()
    assert not (outside / "b.psd").exists()


def test_later_item_parent_escape_blocks_first_item_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "nested/b.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("a.psd", "b.psd")
    plan = create_signature_execution_plan(
        _options(source, output, recursive=True), _rule(), adapter
    )
    original = workflow_module._output_file

    def reject_later(destination: Path, relative: str) -> Path:
        if relative == "nested/b.psd":
            raise ValueError("simulated output ancestry escape")
        return original(destination, relative)

    monkeypatch.setattr(workflow_module, "_output_file", reject_later)

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.processed_count == 0
    assert result.reports_written is False
    assert adapter.replace_calls == []
    assert not (output / "a.psd").exists()


def test_non_directory_output_ancestor_blocks_all_mutation(tmp_path: Path) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "nested/b.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("a.psd", "b.psd")
    plan = create_signature_execution_plan(
        _options(source, output, recursive=True), _rule(), adapter
    )
    (output / "nested").write_bytes(b"NOT_A_DIRECTORY")

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.processed_count == 0
    assert adapter.replace_calls == []
    assert not (output / "a.psd").exists()


def test_preflight_validates_every_planned_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "nested/b.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output", recursive=True),
        _rule(),
        _matching_adapter("a.psd", "b.psd"),
    )
    original = workflow_module._output_file
    checked: list[str] = []

    def recording_output_file(destination: Path, relative: str) -> Path:
        checked.append(relative)
        return original(destination, relative)

    monkeypatch.setattr(workflow_module, "_output_file", recording_output_file)

    validation = validate_execution_plan(plan)

    assert validation.valid is True
    assert checked == ["a.psd", "nested/b.psd"]


def test_event_sink_creates_output_before_mutation_stops_stale(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)
    external = b"EXTERNAL"

    def sink(event: WorkflowEvent) -> None:
        if event.kind is WorkflowEventKind.FILE_STARTED:
            _make_psd(output, "one.psd", external)

    result = execute_signature_plan(plan, adapter, event_sink=sink)

    assert result.stale is True
    assert result.processed_count == 0
    assert result.reports_written is True
    assert adapter.replace_calls == []
    assert (output / "one.psd").read_bytes().endswith(external)


def test_event_sink_changes_source_before_mutation_stops_stale(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    path = _make_psd(source, "one.psd")
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"), _rule(), adapter
    )

    def sink(event: WorkflowEvent) -> None:
        if event.kind is WorkflowEventKind.FILE_STARTED:
            path.write_bytes(path.read_bytes() + b"CHANGED")

    result = execute_signature_plan(plan, adapter, event_sink=sink)

    assert result.stale is True
    assert result.processed_count == 0
    assert result.reports_written is True
    assert adapter.replace_calls == []


def test_output_escape_after_file_started_stops_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "one.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)
    original = workflow_module._output_file
    escape_active = False

    def sink(event: WorkflowEvent) -> None:
        nonlocal escape_active
        if event.kind is WorkflowEventKind.FILE_STARTED:
            escape_active = True

    def race_output_file(destination: Path, relative: str) -> Path:
        if escape_active:
            raise ValueError("simulated output escape")
        return original(destination, relative)

    monkeypatch.setattr(workflow_module, "_output_file", race_output_file)

    result = execute_signature_plan(plan, adapter, event_sink=sink)

    assert result.stale is True
    assert result.processed_count == 0
    assert adapter.replace_calls == []


def test_source_deleted_after_file_started_stops_stale(tmp_path: Path) -> None:
    source = tmp_path / "input"
    path = _make_psd(source, "one.psd")
    adapter = _matching_adapter("one.psd")
    plan = create_signature_execution_plan(
        _options(source, tmp_path / "output"), _rule(), adapter
    )

    def sink(event: WorkflowEvent) -> None:
        if event.kind is WorkflowEventKind.FILE_STARTED:
            path.unlink()

    result = execute_signature_plan(plan, adapter, event_sink=sink)

    assert result.stale is True
    assert result.processed_count == 0
    assert adapter.replace_calls == []


def test_non_stale_photoshop_failure_remains_per_file_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input"
    _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    output = tmp_path / "output"
    adapter = FakeAdapter(
        {
            "a.psd": [_layer("Signature", "OLD")],
            "b.psd": [_layer("Signature", "OLD")],
        },
        replace_errors={"a.psd": PhotoshopReplaceError("replacement failed")},
    )
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    result = execute_signature_plan(plan, adapter)

    assert result.stale is False
    assert result.cancelled is False
    assert result.processed_count == 2
    assert [item.status for item in result.items] == ["FAILED_REPLACE", "REPLACED"]
    assert not (output / "a.psd").exists()
    assert (output / "b.psd").is_file()


def test_filesystem_error_with_changed_boundary_stops_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input"
    first = _make_psd(source, "a.psd")
    _make_psd(source, "b.psd")
    output = tmp_path / "output"
    adapter = _matching_adapter("a.psd", "b.psd")
    plan = create_signature_execution_plan(_options(source, output), _rule(), adapter)

    def filesystem_race(*args, **kwargs):
        first.unlink()
        return {
            "relative_path": "a.psd",
            "status": "FAILED_REPLACE",
            "matched_layer_count": 1,
            "changed_layer_count": 0,
            "old_text": "OLD",
            "new_text": "NEW",
            "output_relative_path": "a.psd",
            "error_code": "FILESYSTEM_ERROR",
            "error_message": "Filesystem operation failed",
        }

    monkeypatch.setattr(
        workflow_module,
        "_execute_planned_replacement",
        filesystem_race,
    )

    result = execute_signature_plan(plan, adapter)

    assert result.stale is True
    assert result.processed_count == 0
    assert result.remaining_count == 2
    assert not (output / "b.psd").exists()

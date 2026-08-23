"""Headless, GUI-safe workflow for planned PSD signature replacement."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable, Mapping

from . import __version__
from .signatures import (
    SignatureAdapter,
    _decision_for_status,
    _execute_planned_replacement,
    _inspect_one_signature,
    _inspection_summary,
    _matching_psd_files,
    _output_file,
    _plan_replacement_candidate,
    _replacement_summary,
    _validate_separate_roots,
    _write_inspection_reports,
    _write_plan_reports,
    _write_replacement_reports,
)
from .workflow_models import (
    CancellationToken,
    ExecutionItemResult,
    ExecutionRunResult,
    InspectItem,
    InspectRunResult,
    OutputSnapshot,
    PlanItem,
    PlanRunResult,
    PlanValidation,
    PlanValidationStatus,
    SignatureExecutionPlan,
    SignatureRule,
    SourceSnapshot,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowEventSink,
    WorkflowOptions,
    WorkflowPhase,
    freeze_summary,
)


EventTarget = WorkflowEventSink | Callable[[WorkflowEvent], None] | None


class WorkflowPlanChangedError(RuntimeError):
    """The candidate state changed while a dry-run plan was being built."""


class WorkflowPlanCancelledError(RuntimeError):
    """A convenience plan request was cancelled before a complete plan existed."""


class _EventDispatcher:
    def __init__(self, target: EventTarget) -> None:
        self._target = target
        self.diagnostics: list[str] = []

    def emit(self, event: WorkflowEvent) -> None:
        if self._target is None:
            return
        try:
            method = getattr(self._target, "emit", None)
            if callable(method):
                method(event)
            else:
                self._target(event)  # type: ignore[operator]
        except Exception:
            self.diagnostics.append("EVENT_SINK_ERROR")


def _normalized_options(options: WorkflowOptions) -> WorkflowOptions:
    source, destination = _validate_separate_roots(
        options.input_dir,
        options.output_dir,
    )
    return WorkflowOptions(
        input_dir=source,
        output_dir=destination,
        recursive=options.recursive,
        include=options.include,
        max_files=options.max_files,
    )


def _candidate_files(options: WorkflowOptions) -> list[Path]:
    return _matching_psd_files(
        options.input_dir,
        recursive=options.recursive,
        include=options.include,
    )


def _relative_paths(root: Path, paths: list[Path]) -> tuple[str, ...]:
    return tuple(path.relative_to(root).as_posix() for path in paths)


def _source_snapshot(root: Path, paths: list[Path]) -> tuple[SourceSnapshot, ...]:
    snapshots: list[SourceSnapshot] = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError as error:
            raise WorkflowPlanChangedError(
                "Source snapshot could not be recorded"
            ) from error
        snapshots.append(
            SourceSnapshot(
                relative_path=path.relative_to(root).as_posix(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )
    return tuple(snapshots)


def _one_output_snapshot(output_dir: Path, relative: str) -> OutputSnapshot:
    path = output_dir / Path(relative)
    is_symlink = path.is_symlink()
    exists = path.exists() or is_symlink
    if not exists:
        return OutputSnapshot(relative, False, False, None, None)
    try:
        stat = path.lstat()
    except OSError as error:
        raise WorkflowPlanChangedError(
            "Output snapshot could not be recorded"
        ) from error
    return OutputSnapshot(
        relative_path=relative,
        exists=True,
        is_symlink=is_symlink,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _output_snapshot(
    output_dir: Path,
    relatives: tuple[str, ...],
) -> tuple[OutputSnapshot, ...]:
    return tuple(_one_output_snapshot(output_dir, relative) for relative in relatives)


def _plan_payload(
    *,
    options: WorkflowOptions,
    rule: SignatureRule,
    candidate_relative_paths: tuple[str, ...],
    source_snapshot: tuple[SourceSnapshot, ...],
    output_snapshot: tuple[OutputSnapshot, ...],
    items: tuple[PlanItem, ...],
    max_files_reached: bool,
) -> dict:
    return {
        "schema": 1,
        "options": {
            "input_dir": str(options.input_dir),
            "output_dir": str(options.output_dir),
            "recursive": options.recursive,
            "include": options.include,
            "max_files": options.max_files,
        },
        "rule": {
            "old_text": rule.old_text,
            "new_text": rule.new_text,
            "layer_name": rule.layer_name,
        },
        "candidate_relative_paths": list(candidate_relative_paths),
        "source_snapshot": [
            {
                "relative_path": item.relative_path,
                "size": item.size,
                "mtime_ns": item.mtime_ns,
            }
            for item in source_snapshot
        ],
        "output_snapshot": [
            {
                "relative_path": item.relative_path,
                "exists": item.exists,
                "is_symlink": item.is_symlink,
                "size": item.size,
                "mtime_ns": item.mtime_ns,
            }
            for item in output_snapshot
        ],
        "items": [
            {
                "relative_path": item.relative_path,
                "decision": item.decision,
                "matched_layer_count": item.matched_layer_count,
                "output_relative_path": item.output_relative_path,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "formal_status": item.formal_status,
            }
            for item in items
        ],
        "max_files_reached": max_files_reached,
    }


def _plan_id_from_parts(
    *,
    options: WorkflowOptions,
    rule: SignatureRule,
    candidate_relative_paths: tuple[str, ...],
    source_snapshot: tuple[SourceSnapshot, ...],
    output_snapshot: tuple[OutputSnapshot, ...],
    items: tuple[PlanItem, ...],
    max_files_reached: bool,
) -> str:
    payload = _plan_payload(
        options=options,
        rule=rule,
        candidate_relative_paths=candidate_relative_paths,
        source_snapshot=source_snapshot,
        output_snapshot=output_snapshot,
        items=items,
        max_files_reached=max_files_reached,
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _expected_plan_id(plan: SignatureExecutionPlan) -> str:
    return _plan_id_from_parts(
        options=plan.options,
        rule=plan.rule,
        candidate_relative_paths=plan.candidate_relative_paths,
        source_snapshot=plan.source_snapshot,
        output_snapshot=plan.output_snapshot,
        items=plan.items,
        max_files_reached=plan.max_files_reached,
    )


def inspect_signature_workflow(
    options: WorkflowOptions,
    adapter: SignatureAdapter,
    *,
    layer_name: str | None = None,
    contains_text: str | None = None,
    cancellation_token: CancellationToken | None = None,
    event_sink: EventTarget = None,
) -> InspectRunResult:
    """Run inspect with in-memory rows, structured events, and safe cancellation."""

    normalized = _normalized_options(options)
    candidates = _candidate_files(normalized)
    files = candidates[: normalized.max_files]
    truncated = len(candidates) > normalized.max_files
    normalized.output_dir.mkdir(parents=True, exist_ok=True)
    token = cancellation_token or CancellationToken()
    events = _EventDispatcher(event_sink)
    total = len(files)
    events.emit(
        WorkflowEvent(
            WorkflowPhase.INSPECT,
            WorkflowEventKind.RUN_STARTED,
            0,
            total,
        )
    )

    rows: list[dict] = []
    opened_count = 0
    layer_count = 0
    matched_count = 0
    error_count = 0
    processed = 0
    for index, path in enumerate(files, start=1):
        if token.cancelled:
            break
        relative = path.relative_to(normalized.input_dir).as_posix()
        events.emit(
            WorkflowEvent(
                WorkflowPhase.INSPECT,
                WorkflowEventKind.FILE_STARTED,
                index,
                total,
                relative,
            )
        )
        file_rows, opened, layers, matched, errors = _inspect_one_signature(
            path,
            relative,
            adapter,
            layer_name=layer_name,
            contains_text=contains_text,
        )
        rows.extend(file_rows)
        opened_count += opened
        layer_count += layers
        matched_count += matched
        error_count += errors
        processed += 1
        status = file_rows[0]["error"] or "INSPECTED"
        events.emit(
            WorkflowEvent(
                WorkflowPhase.INSPECT,
                WorkflowEventKind.FILE_RESULT,
                index,
                total,
                relative,
                status,
            )
        )

    cancelled = processed < total and token.cancelled
    summary = _inspection_summary(
        file_count=total,
        opened_count=opened_count,
        layer_count=layer_count,
        matched_count=matched_count,
        error_count=error_count,
        truncated=truncated,
    )
    _write_inspection_reports(normalized.output_dir, rows, summary)
    events.emit(
        WorkflowEvent(
            WorkflowPhase.INSPECT,
            (
                WorkflowEventKind.RUN_CANCELLED
                if cancelled
                else WorkflowEventKind.RUN_COMPLETED
            ),
            processed,
            total,
        )
    )
    return InspectRunResult(
        items=tuple(InspectItem(**row) for row in rows),
        summary=freeze_summary(summary),
        processed_count=processed,
        remaining_count=total - processed,
        cancelled=cancelled,
        stale=False,
        max_files_reached=truncated,
        candidate_count=len(candidates),
        selected_count=total,
        diagnostics=tuple(events.diagnostics),
    )


def _plan_run_result(
    *,
    plan: SignatureExecutionPlan | None,
    items: list[PlanItem],
    rows: list[dict],
    events: _EventDispatcher,
    selected_count: int,
    candidate_count: int,
    cancelled: bool,
    stale: bool,
    max_files_reached: bool,
) -> PlanRunResult:
    summary = _replacement_summary(
        rows,
        file_count=selected_count,
        truncated=max_files_reached,
        dry_run=True,
    )
    return PlanRunResult(
        plan=plan,
        items=tuple(items),
        summary=freeze_summary(summary),
        processed_count=len(items),
        remaining_count=selected_count - len(items),
        cancelled=cancelled,
        stale=stale,
        max_files_reached=max_files_reached,
        candidate_count=candidate_count,
        selected_count=selected_count,
        diagnostics=tuple(events.diagnostics),
    )


def _plan_signature_workflow_engine(
    options: WorkflowOptions,
    rule: SignatureRule,
    adapter: SignatureAdapter,
    *,
    cancellation_token: CancellationToken | None = None,
    event_sink: EventTarget = None,
) -> PlanRunResult:
    """Build a plan cooperatively; partial runs never return an executable plan."""

    normalized = _normalized_options(options)
    candidates = _candidate_files(normalized)
    candidate_relatives = _relative_paths(normalized.input_dir, candidates)
    files = candidates[: normalized.max_files]
    truncated = len(candidates) > normalized.max_files
    selected_relatives = _relative_paths(normalized.input_dir, files)
    sources_before = _source_snapshot(normalized.input_dir, files)
    outputs_before = _output_snapshot(normalized.output_dir, selected_relatives)
    token = cancellation_token or CancellationToken()
    events = _EventDispatcher(event_sink)
    total = len(files)
    events.emit(
        WorkflowEvent(
            WorkflowPhase.DRY_RUN,
            WorkflowEventKind.RUN_STARTED,
            0,
            total,
        )
    )

    rows: list[dict] = []
    plan_items: list[PlanItem] = []
    for index, source_path in enumerate(files, start=1):
        if token.cancelled:
            break
        relative = source_path.relative_to(normalized.input_dir).as_posix()
        events.emit(
            WorkflowEvent(
                WorkflowPhase.DRY_RUN,
                WorkflowEventKind.FILE_STARTED,
                index,
                total,
                relative,
            )
        )
        row = _plan_replacement_candidate(
            source_path,
            normalized.input_dir,
            normalized.output_dir,
            adapter,
            old_text=rule.old_text,
            new_text=rule.new_text,
            layer_name=rule.layer_name,
        )
        rows.append(row)
        decision = _decision_for_status(row["status"])
        plan_items.append(
            PlanItem(
                relative_path=relative,
                decision=decision,
                matched_layer_count=row["matched_layer_count"],
                output_relative_path=row["output_relative_path"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                formal_status=row["status"] if decision == "ERROR" else "",
            )
        )
        events.emit(
            WorkflowEvent(
                WorkflowPhase.DRY_RUN,
                WorkflowEventKind.FILE_RESULT,
                index,
                total,
                relative,
                decision,
            )
        )

    cancelled = len(plan_items) < total and token.cancelled
    if cancelled:
        events.emit(
            WorkflowEvent(
                WorkflowPhase.DRY_RUN,
                WorkflowEventKind.RUN_CANCELLED,
                len(plan_items),
                total,
            )
        )
        return _plan_run_result(
            plan=None,
            items=plan_items,
            rows=rows,
            events=events,
            selected_count=total,
            candidate_count=len(candidates),
            cancelled=True,
            stale=False,
            max_files_reached=truncated,
        )

    stale_status: PlanValidationStatus | None = None
    try:
        candidates_after = _candidate_files(normalized)
        if _relative_paths(normalized.input_dir, candidates_after) != candidate_relatives:
            stale_status = PlanValidationStatus.STALE_SOURCE_SET
    except (OSError, ValueError):
        stale_status = PlanValidationStatus.STALE_SOURCE_SET
    if stale_status is None:
        try:
            if _source_snapshot(normalized.input_dir, files) != sources_before:
                stale_status = PlanValidationStatus.STALE_SOURCE_FILE
        except WorkflowPlanChangedError:
            stale_status = PlanValidationStatus.STALE_SOURCE_FILE
    if stale_status is None:
        try:
            for relative in selected_relatives:
                _output_file(normalized.output_dir, relative)
            if _output_snapshot(normalized.output_dir, selected_relatives) != outputs_before:
                stale_status = PlanValidationStatus.STALE_OUTPUT
        except (ValueError, WorkflowPlanChangedError):
            stale_status = PlanValidationStatus.STALE_OUTPUT

    if stale_status is not None:
        events.emit(
            WorkflowEvent(
                WorkflowPhase.DRY_RUN,
                WorkflowEventKind.RUN_STOPPED_STALE,
                len(plan_items),
                total,
                status=stale_status.value,
            )
        )
        return _plan_run_result(
            plan=None,
            items=plan_items,
            rows=rows,
            events=events,
            selected_count=total,
            candidate_count=len(candidates),
            cancelled=False,
            stale=True,
            max_files_reached=truncated,
        )

    summary = _replacement_summary(
        rows,
        file_count=total,
        truncated=truncated,
        dry_run=True,
    )
    normalized.output_dir.mkdir(parents=True, exist_ok=True)
    _write_plan_reports(normalized.output_dir, rows, summary)
    items = tuple(plan_items)
    plan_id = _plan_id_from_parts(
        options=normalized,
        rule=rule,
        candidate_relative_paths=candidate_relatives,
        source_snapshot=sources_before,
        output_snapshot=outputs_before,
        items=items,
        max_files_reached=truncated,
    )
    events.emit(
        WorkflowEvent(
            WorkflowPhase.DRY_RUN,
            WorkflowEventKind.RUN_COMPLETED,
            total,
            total,
        )
    )
    plan = SignatureExecutionPlan(
        plan_id=plan_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        options=normalized,
        rule=rule,
        candidate_relative_paths=candidate_relatives,
        source_snapshot=sources_before,
        output_snapshot=outputs_before,
        items=items,
        max_files_reached=truncated,
        diagnostics=tuple(events.diagnostics),
    )
    return _plan_run_result(
        plan=plan,
        items=plan_items,
        rows=rows,
        events=events,
        selected_count=total,
        candidate_count=len(candidates),
        cancelled=False,
        stale=False,
        max_files_reached=truncated,
    )


def plan_signature_workflow(
    options: WorkflowOptions,
    rule: SignatureRule,
    adapter: SignatureAdapter,
    *,
    cancellation_token: CancellationToken | None = None,
    event_sink: EventTarget = None,
) -> PlanRunResult:
    """Create a cancellable dry-run result for a future GUI/controller."""

    return _plan_signature_workflow_engine(
        options,
        rule,
        adapter,
        cancellation_token=cancellation_token,
        event_sink=event_sink,
    )


def create_signature_execution_plan(
    options: WorkflowOptions,
    rule: SignatureRule,
    adapter: SignatureAdapter,
    *,
    cancellation_token: CancellationToken | None = None,
    event_sink: EventTarget = None,
) -> SignatureExecutionPlan:
    """Convenience wrapper requiring a complete, executable dry-run plan."""

    result = _plan_signature_workflow_engine(
        options,
        rule,
        adapter,
        cancellation_token=cancellation_token,
        event_sink=event_sink,
    )
    if result.cancelled:
        raise WorkflowPlanCancelledError("Plan generation was cancelled")
    if result.stale or result.plan is None:
        raise WorkflowPlanChangedError("Plan state changed during generation")
    return result.plan


def _options_match(current: WorkflowOptions, expected: WorkflowOptions) -> bool:
    try:
        return _normalized_options(current) == expected
    except (OSError, ValueError):
        return False


def validate_execution_plan(
    plan: SignatureExecutionPlan,
    *,
    current_options: WorkflowOptions | None = None,
    current_rule: SignatureRule | None = None,
) -> PlanValidation:
    """Validate immutable parameters plus current source and output state."""

    if _expected_plan_id(plan) != plan.plan_id:
        return PlanValidation(PlanValidationStatus.STALE_PARAMETERS)
    if current_options is not None and not _options_match(current_options, plan.options):
        return PlanValidation(PlanValidationStatus.STALE_PARAMETERS)
    if current_rule is not None and current_rule != plan.rule:
        return PlanValidation(PlanValidationStatus.STALE_PARAMETERS)

    source = plan.options.input_dir
    if not source.is_dir() or source.is_symlink():
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_SET)
    try:
        candidates = _candidate_files(plan.options)
    except (OSError, ValueError):
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_SET)
    candidate_relatives = _relative_paths(source, candidates)
    if candidate_relatives != plan.candidate_relative_paths:
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_SET)
    selected = candidates[: plan.options.max_files]
    truncated = len(candidates) > plan.options.max_files
    if truncated != plan.max_files_reached:
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_SET)
    if _relative_paths(source, selected) != tuple(
        item.relative_path for item in plan.source_snapshot
    ):
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_SET)
    for expected in plan.source_snapshot:
        path = source / Path(expected.relative_path)
        try:
            stat = path.stat()
        except OSError:
            return PlanValidation(
                PlanValidationStatus.STALE_SOURCE_FILE,
                expected.relative_path,
            )
        if stat.st_size != expected.size or stat.st_mtime_ns != expected.mtime_ns:
            return PlanValidation(
                PlanValidationStatus.STALE_SOURCE_FILE,
                expected.relative_path,
            )

    output = plan.options.output_dir
    try:
        if output.exists() and output.resolve(strict=False) != output:
            return PlanValidation(PlanValidationStatus.STALE_OUTPUT)
    except OSError:
        return PlanValidation(PlanValidationStatus.STALE_OUTPUT)
    for expected in plan.output_snapshot:
        try:
            _output_file(output, expected.relative_path)
            current = _one_output_snapshot(output, expected.relative_path)
        except (ValueError, WorkflowPlanChangedError):
            return PlanValidation(
                PlanValidationStatus.STALE_OUTPUT,
                expected.relative_path,
            )
        if current != expected:
            return PlanValidation(
                PlanValidationStatus.STALE_OUTPUT,
                expected.relative_path,
            )
    return PlanValidation(PlanValidationStatus.VALID)


def _validate_item_boundary(
    plan: SignatureExecutionPlan,
    relative: str,
) -> PlanValidation:
    source_expected = next(
        item for item in plan.source_snapshot if item.relative_path == relative
    )
    source_path = plan.options.input_dir / Path(relative)
    try:
        stat = source_path.stat()
    except OSError:
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_FILE, relative)
    if stat.st_size != source_expected.size or stat.st_mtime_ns != source_expected.mtime_ns:
        return PlanValidation(PlanValidationStatus.STALE_SOURCE_FILE, relative)

    output_expected = next(
        item for item in plan.output_snapshot if item.relative_path == relative
    )
    try:
        current = _one_output_snapshot(plan.options.output_dir, relative)
        _output_file(plan.options.output_dir, relative)
    except (ValueError, WorkflowPlanChangedError):
        return PlanValidation(PlanValidationStatus.STALE_OUTPUT, relative)
    if current != output_expected:
        return PlanValidation(PlanValidationStatus.STALE_OUTPUT, relative)
    return PlanValidation(PlanValidationStatus.VALID)


def _formal_row_from_plan_item(plan: SignatureExecutionPlan, item: PlanItem) -> dict:
    status = {
        "SKIP_NO_MATCH": "SKIPPED_NO_MATCH",
        "SKIP_AMBIGUOUS": "SKIPPED_AMBIGUOUS",
        "SKIP_EXISTS": "SKIPPED_EXISTS",
        "ERROR": item.formal_status or "FAILED_REPLACE",
    }[item.decision]
    return {
        "relative_path": item.relative_path,
        "status": status,
        "matched_layer_count": item.matched_layer_count,
        "changed_layer_count": 0,
        "old_text": plan.rule.old_text,
        "new_text": plan.rule.new_text,
        "output_relative_path": item.output_relative_path,
        "error_code": item.error_code,
        "error_message": item.error_message,
    }


def _typed_execution_item(row: Mapping[str, object]) -> ExecutionItemResult:
    return ExecutionItemResult(
        relative_path=str(row["relative_path"]),
        status=str(row["status"]),
        matched_layer_count=int(row["matched_layer_count"]),
        changed_layer_count=int(row["changed_layer_count"]),
        output_relative_path=str(row["output_relative_path"]),
        error_code=str(row["error_code"]),
        error_message=str(row["error_message"]),
    )


def _execution_result(
    plan: SignatureExecutionPlan,
    rows: list[dict],
    events: _EventDispatcher,
    *,
    cancelled: bool,
    stale: bool,
    workflow_status: str,
    write_reports: bool,
) -> ExecutionRunResult:
    total = len(plan.items)
    summary = _replacement_summary(
        rows,
        file_count=total,
        truncated=plan.max_files_reached,
        dry_run=False,
    )
    if write_reports:
        plan.options.output_dir.mkdir(parents=True, exist_ok=True)
        _write_replacement_reports(plan.options.output_dir, rows, summary)
    return ExecutionRunResult(
        plan_id=plan.plan_id,
        items=tuple(_typed_execution_item(row) for row in rows),
        summary=freeze_summary(summary),
        processed_count=len(rows),
        remaining_count=total - len(rows),
        cancelled=cancelled,
        stale=stale,
        max_files_reached=plan.max_files_reached,
        candidate_count=plan.candidate_count,
        selected_count=plan.selected_count,
        workflow_status=workflow_status,
        diagnostics=tuple(plan.diagnostics) + tuple(events.diagnostics),
        reports_written=write_reports,
    )


def execute_signature_plan(
    plan: SignatureExecutionPlan,
    adapter: SignatureAdapter,
    *,
    cancellation_token: CancellationToken | None = None,
    event_sink: EventTarget = None,
) -> ExecutionRunResult:
    """Execute only the immutable plan; no replacement parameters are accepted."""

    if not isinstance(plan, SignatureExecutionPlan):
        raise TypeError("a complete SignatureExecutionPlan is required")
    token = cancellation_token or CancellationToken()
    events = _EventDispatcher(event_sink)
    total = len(plan.items)
    events.emit(
        WorkflowEvent(
            WorkflowPhase.EXECUTION,
            WorkflowEventKind.RUN_STARTED,
            0,
            total,
        )
    )
    preflight = validate_execution_plan(plan)
    if not preflight.valid:
        events.emit(
            WorkflowEvent(
                WorkflowPhase.EXECUTION,
                WorkflowEventKind.RUN_STOPPED_STALE,
                0,
                total,
                preflight.relative_path,
                preflight.status.value,
            )
        )
        return _execution_result(
            plan,
            [],
            events,
            cancelled=False,
            stale=True,
            workflow_status="EXECUTION_STOPPED_PLAN_STALE",
            write_reports=False,
        )

    if token.cancelled:
        events.emit(
            WorkflowEvent(
                WorkflowPhase.EXECUTION,
                WorkflowEventKind.RUN_CANCELLED,
                0,
                total,
            )
        )
        return _execution_result(
            plan,
            [],
            events,
            cancelled=True,
            stale=False,
            workflow_status="EXECUTION_CANCELLED",
            write_reports=True,
        )

    rows: list[dict] = []
    stopped_stale = False
    for index, item in enumerate(plan.items, start=1):
        if token.cancelled:
            break
        boundary = _validate_item_boundary(plan, item.relative_path)
        if not boundary.valid:
            stopped_stale = True
            events.emit(
                WorkflowEvent(
                    WorkflowPhase.EXECUTION,
                    WorkflowEventKind.RUN_STOPPED_STALE,
                    len(rows),
                    total,
                    item.relative_path,
                    boundary.status.value,
                )
            )
            break
        events.emit(
            WorkflowEvent(
                WorkflowPhase.EXECUTION,
                WorkflowEventKind.FILE_STARTED,
                index,
                total,
                item.relative_path,
            )
        )
        final_boundary = _validate_item_boundary(plan, item.relative_path)
        if not final_boundary.valid:
            stopped_stale = True
            events.emit(
                WorkflowEvent(
                    WorkflowPhase.EXECUTION,
                    WorkflowEventKind.FILE_RESULT,
                    index,
                    total,
                    item.relative_path,
                    "EXECUTION_STOPPED_PLAN_STALE",
                )
            )
            events.emit(
                WorkflowEvent(
                    WorkflowPhase.EXECUTION,
                    WorkflowEventKind.RUN_STOPPED_STALE,
                    len(rows),
                    total,
                    item.relative_path,
                    final_boundary.status.value,
                )
            )
            break

        if item.decision == "WOULD_REPLACE":
            source_path = plan.options.input_dir / Path(item.relative_path)
            row = _execute_planned_replacement(
                source_path,
                plan.options.output_dir,
                item.relative_path,
                adapter,
                old_text=plan.rule.old_text,
                new_text=plan.rule.new_text,
                layer_name=plan.rule.layer_name,
            )
            if row["status"] == "SKIPPED_EXISTS":
                stopped_stale = True
                events.emit(
                    WorkflowEvent(
                        WorkflowPhase.EXECUTION,
                        WorkflowEventKind.FILE_RESULT,
                        index,
                        total,
                        item.relative_path,
                        "EXECUTION_STOPPED_PLAN_STALE",
                    )
                )
                events.emit(
                    WorkflowEvent(
                        WorkflowPhase.EXECUTION,
                        WorkflowEventKind.RUN_STOPPED_STALE,
                        len(rows),
                        total,
                        item.relative_path,
                        PlanValidationStatus.STALE_OUTPUT.value,
                    )
                )
                break
            if row["error_code"].startswith("OUTPUT_PATH_ESCAPE"):
                stopped_stale = True
                events.emit(
                    WorkflowEvent(
                        WorkflowPhase.EXECUTION,
                        WorkflowEventKind.FILE_RESULT,
                        index,
                        total,
                        item.relative_path,
                        "EXECUTION_STOPPED_PLAN_STALE",
                    )
                )
                events.emit(
                    WorkflowEvent(
                        WorkflowPhase.EXECUTION,
                        WorkflowEventKind.RUN_STOPPED_STALE,
                        len(rows),
                        total,
                        item.relative_path,
                        PlanValidationStatus.STALE_OUTPUT.value,
                    )
                )
                break
            if row["error_code"].startswith("FILESYSTEM_ERROR"):
                race_boundary = _validate_item_boundary(plan, item.relative_path)
                if not race_boundary.valid:
                    stopped_stale = True
                    events.emit(
                        WorkflowEvent(
                            WorkflowPhase.EXECUTION,
                            WorkflowEventKind.FILE_RESULT,
                            index,
                            total,
                            item.relative_path,
                            "EXECUTION_STOPPED_PLAN_STALE",
                        )
                    )
                    events.emit(
                        WorkflowEvent(
                            WorkflowPhase.EXECUTION,
                            WorkflowEventKind.RUN_STOPPED_STALE,
                            len(rows),
                            total,
                            item.relative_path,
                            race_boundary.status.value,
                        )
                    )
                    break
        else:
            row = _formal_row_from_plan_item(plan, item)

        rows.append(row)
        events.emit(
            WorkflowEvent(
                WorkflowPhase.EXECUTION,
                WorkflowEventKind.FILE_RESULT,
                index,
                total,
                item.relative_path,
                row["status"],
            )
        )
        if row["error_code"].startswith("MATCH_CHANGED_BEFORE_SAVE"):
            stopped_stale = True
            events.emit(
                WorkflowEvent(
                    WorkflowPhase.EXECUTION,
                    WorkflowEventKind.RUN_STOPPED_STALE,
                    len(rows),
                    total,
                    item.relative_path,
                    PlanValidationStatus.STALE_SOURCE_FILE.value,
                )
            )
            break

    if stopped_stale:
        return _execution_result(
            plan,
            rows,
            events,
            cancelled=False,
            stale=True,
            workflow_status="EXECUTION_STOPPED_PLAN_STALE",
            write_reports=True,
        )

    cancelled = len(rows) < total and token.cancelled
    events.emit(
        WorkflowEvent(
            WorkflowPhase.EXECUTION,
            (
                WorkflowEventKind.RUN_CANCELLED
                if cancelled
                else WorkflowEventKind.RUN_COMPLETED
            ),
            len(rows),
            total,
        )
    )
    return _execution_result(
        plan,
        rows,
        events,
        cancelled=cancelled,
        stale=False,
        workflow_status=("EXECUTION_CANCELLED" if cancelled else "RESULT"),
        write_reports=True,
    )


def build_public_diagnostic(
    result: (
        InspectRunResult
        | PlanRunResult
        | SignatureExecutionPlan
        | ExecutionRunResult
    ),
) -> dict:
    """Build a local/public-safe summary without paths, filenames, or text."""

    if isinstance(result, SignatureExecutionPlan):
        status_counts = dict(
            sorted(Counter(item.decision for item in result.items).items())
        )
        error_codes = sorted(
            {item.error_code for item in result.items if item.error_code}
        )
        return {
            "app_version": __version__,
            "phase": "DRY_RUN_REVIEW",
            "file_count": len(result.items),
            "processed_count": len(result.items),
            "remaining_count": 0,
            "candidate_count": result.candidate_count,
            "selected_count": result.selected_count,
            "unplanned_count": result.unplanned_count,
            "partial_plan": result.partial_plan,
            "planned_items_complete": True,
            "corpus_complete": not result.partial_plan,
            "status_counts": status_counts,
            "max_files_reached": result.max_files_reached,
            "cancelled": False,
            "stale": False,
            "error_codes": error_codes,
            "diagnostics": sorted(set(result.diagnostics)),
        }

    if isinstance(result, PlanRunResult):
        error_codes = sorted(
            {item.error_code for item in result.items if item.error_code}
        )
        phase = (
            "DRY_RUN_CANCELLED"
            if result.cancelled
            else "DRY_RUN_STOPPED_STALE"
            if result.stale
            else "DRY_RUN_REVIEW"
        )
        status_counts = result.summary.get("status_counts", {})
        return {
            "app_version": __version__,
            "phase": phase,
            "file_count": int(result.summary.get("file_count", 0)),
            "processed_count": result.processed_count,
            "remaining_count": result.remaining_count,
            "candidate_count": result.candidate_count,
            "selected_count": result.selected_count,
            "unplanned_count": result.unplanned_count,
            "partial_plan": result.partial_plan,
            "planned_items_complete": result.planned_items_complete,
            "corpus_complete": result.corpus_complete,
            "status_counts": (
                dict(status_counts) if isinstance(status_counts, Mapping) else {}
            ),
            "max_files_reached": result.max_files_reached,
            "cancelled": result.cancelled,
            "stale": result.stale,
            "error_codes": error_codes,
            "diagnostics": sorted(set(result.diagnostics)),
        }

    status_counts = result.summary.get("status_counts", {})
    if isinstance(result, ExecutionRunResult):
        error_codes = sorted(
            {item.error_code for item in result.items if item.error_code}
        )
        phase = result.workflow_status
    else:
        error_codes = sorted({item.error for item in result.items if item.error})
        phase = "INSPECT"
    diagnostic = {
        "app_version": __version__,
        "phase": phase,
        "file_count": int(result.summary.get("file_count", 0)),
        "processed_count": result.processed_count,
        "remaining_count": result.remaining_count,
        "candidate_count": result.candidate_count,
        "selected_count": result.selected_count,
        "unplanned_count": result.unplanned_count,
        "partial_plan": result.partial_plan,
        "planned_items_complete": result.planned_items_complete,
        "corpus_complete": result.corpus_complete,
        "status_counts": dict(status_counts) if isinstance(status_counts, Mapping) else {},
        "max_files_reached": result.max_files_reached,
        "cancelled": result.cancelled,
        "stale": result.stale,
        "error_codes": error_codes,
        "diagnostics": sorted(set(result.diagnostics)),
    }
    if isinstance(result, ExecutionRunResult):
        diagnostic["reports_written"] = result.reports_written
    return diagnostic

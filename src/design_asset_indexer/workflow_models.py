"""Immutable models for the headless signature workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event
from types import MappingProxyType
from typing import Mapping, Protocol


class WorkflowPhase(str, Enum):
    INSPECT = "INSPECT"
    DRY_RUN = "DRY_RUN"
    EXECUTION = "EXECUTION"


class WorkflowEventKind(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    FILE_STARTED = "FILE_STARTED"
    FILE_RESULT = "FILE_RESULT"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_CANCELLED = "RUN_CANCELLED"
    RUN_STOPPED_STALE = "RUN_STOPPED_STALE"


class PlanValidationStatus(str, Enum):
    VALID = "VALID"
    STALE_PARAMETERS = "STALE_PARAMETERS"
    STALE_SOURCE_SET = "STALE_SOURCE_SET"
    STALE_SOURCE_FILE = "STALE_SOURCE_FILE"
    STALE_OUTPUT = "STALE_OUTPUT"


@dataclass(frozen=True)
class SignatureRule:
    old_text: str
    new_text: str
    layer_name: str | None = None

    def __post_init__(self) -> None:
        if not self.old_text:
            raise ValueError("source text must not be empty")
        if not self.new_text:
            raise ValueError("replacement text must not be empty")
        if self.old_text == self.new_text:
            raise ValueError("source and replacement text must differ")


@dataclass(frozen=True)
class WorkflowOptions:
    input_dir: Path
    output_dir: Path
    recursive: bool = False
    include: str = "*.psd"
    max_files: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.input_dir, Path) or not isinstance(self.output_dir, Path):
            raise TypeError("workflow paths must be pathlib.Path values")
        if not self.include:
            raise ValueError("include pattern must not be empty")
        if self.max_files < 1:
            raise ValueError("maximum file count must be positive")


@dataclass(frozen=True)
class SourceSnapshot:
    relative_path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class OutputSnapshot:
    relative_path: str
    exists: bool
    is_symlink: bool
    size: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class PlanItem:
    relative_path: str
    decision: str
    matched_layer_count: int
    output_relative_path: str
    error_code: str = ""
    error_message: str = ""
    formal_status: str = ""


@dataclass(frozen=True)
class SignatureExecutionPlan:
    plan_id: str
    created_at: str
    options: WorkflowOptions
    rule: SignatureRule
    candidate_relative_paths: tuple[str, ...]
    source_snapshot: tuple[SourceSnapshot, ...]
    output_snapshot: tuple[OutputSnapshot, ...]
    items: tuple[PlanItem, ...]
    max_files_reached: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanValidation:
    status: PlanValidationStatus
    relative_path: str | None = None

    @property
    def valid(self) -> bool:
        return self.status is PlanValidationStatus.VALID


@dataclass(frozen=True)
class WorkflowEvent:
    phase: WorkflowPhase
    kind: WorkflowEventKind
    index: int
    total: int
    relative_path: str | None = None
    status: str | None = None


class WorkflowEventSink(Protocol):
    def emit(self, event: WorkflowEvent) -> None: ...


class CancellationToken:
    """Thread-safe cooperative cancellation checked only at file boundaries."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True)
class InspectItem:
    relative_path: str
    document_opened: bool
    layer_path: str
    layer_name: str
    layer_kind: str
    current_text: str
    matched: bool
    error: str


@dataclass(frozen=True)
class ExecutionItemResult:
    relative_path: str
    status: str
    matched_layer_count: int
    changed_layer_count: int
    output_relative_path: str
    error_code: str = ""
    error_message: str = ""


def freeze_summary(summary: Mapping[str, object]) -> Mapping[str, object]:
    """Return a shallow immutable summary with an immutable status-count map."""

    frozen = dict(summary)
    status_counts = frozen.get("status_counts")
    if isinstance(status_counts, Mapping):
        frozen["status_counts"] = MappingProxyType(dict(status_counts))
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class InspectRunResult:
    items: tuple[InspectItem, ...]
    summary: Mapping[str, object]
    processed_count: int
    remaining_count: int
    cancelled: bool
    stale: bool
    max_files_reached: bool
    diagnostics: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.cancelled and not self.stale and self.remaining_count == 0


@dataclass(frozen=True)
class ExecutionRunResult:
    plan_id: str
    items: tuple[ExecutionItemResult, ...]
    summary: Mapping[str, object]
    processed_count: int
    remaining_count: int
    cancelled: bool
    stale: bool
    max_files_reached: bool
    workflow_status: str
    diagnostics: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.cancelled and not self.stale and self.remaining_count == 0

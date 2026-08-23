"""QThread workers that own the complete Photoshop COM lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import sys
from typing import Callable, Protocol

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..photoshop import PhotoshopAdapter, PhotoshopAutomationError
from ..workflow import (
    execute_signature_plan,
    inspect_signature_workflow,
    plan_signature_workflow,
)
from ..workflow_models import (
    CancellationToken,
    SignatureExecutionPlan,
    SignatureRule,
    WorkflowEvent,
    WorkflowOptions,
)


class WorkerOperation(str, Enum):
    ENVIRONMENT = "environment"
    INSPECT = "inspect"
    PLAN = "plan"
    EXECUTE = "execute"


@dataclass(frozen=True)
class EnvironmentCheckResult:
    available: bool
    version: str | None
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class WorkerRequest:
    operation: WorkerOperation
    cancellation_token: CancellationToken
    options: WorkflowOptions | None = None
    rule: SignatureRule | None = None
    plan: SignatureExecutionPlan | None = None


@dataclass(frozen=True)
class _TerminalOutcome:
    kind: str
    payload: object


class ComRuntime(Protocol):
    def CoInitialize(self) -> None: ...  # noqa: N802

    def CoUninitialize(self) -> None: ...  # noqa: N802


class _NullComRuntime:
    def CoInitialize(self) -> None:  # noqa: N802
        return None

    def CoUninitialize(self) -> None:  # noqa: N802
        return None


def _default_com_runtime() -> ComRuntime:
    if sys.platform == "win32":
        import pythoncom  # type: ignore[import-not-found]

        return pythoncom
    return _NullComRuntime()


AdapterFactory = Callable[[], object]
ComRuntimeFactory = Callable[[], ComRuntime]


class WorkflowWorker(QObject):
    """Execute exactly one Photoshop phase inside its owning worker thread."""

    event = Signal(object)
    completed = Signal(object)
    environment_ready = Signal(object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        request: WorkerRequest,
        *,
        adapter_factory: AdapterFactory = PhotoshopAdapter,
        com_runtime_factory: ComRuntimeFactory = _default_com_runtime,
    ) -> None:
        super().__init__()
        self.request = request
        self._adapter_factory = adapter_factory
        self._com_runtime_factory = com_runtime_factory

    def _emit_event(self, event: WorkflowEvent) -> None:
        self.event.emit(event)

    @staticmethod
    def _failure_outcome(error: Exception) -> _TerminalOutcome:
        if isinstance(error, PhotoshopAutomationError):
            return _TerminalOutcome("failed", (str(error.code), str(error)))
        return _TerminalOutcome(
            "failed",
            (type(error).__name__.upper(), "Photoshop workflow failed"),
        )

    def _operation_outcome(self) -> _TerminalOutcome:
        """Run one operation while keeping the adapter inside this local scope."""

        adapter: object | None = None
        try:
            adapter = self._adapter_factory()
            operation = self.request.operation
            if operation is WorkerOperation.ENVIRONMENT:
                available = bool(adapter.is_available())  # type: ignore[attr-defined]
                version = str(adapter.version) if available else None  # type: ignore[attr-defined]
                return _TerminalOutcome(
                    "environment_ready",
                    EnvironmentCheckResult(available, version),
                )
            if operation is WorkerOperation.INSPECT:
                if self.request.options is None:
                    raise ValueError("inspect options are missing")
                result = inspect_signature_workflow(
                    self.request.options,
                    adapter,  # type: ignore[arg-type]
                    cancellation_token=self.request.cancellation_token,
                    event_sink=self._emit_event,
                )
                return _TerminalOutcome("completed", result)
            if operation is WorkerOperation.PLAN:
                if self.request.options is None or self.request.rule is None:
                    raise ValueError("plan parameters are missing")
                result = plan_signature_workflow(
                    self.request.options,
                    self.request.rule,
                    adapter,  # type: ignore[arg-type]
                    cancellation_token=self.request.cancellation_token,
                    event_sink=self._emit_event,
                )
                return _TerminalOutcome("completed", result)
            if operation is WorkerOperation.EXECUTE:
                if self.request.plan is None:
                    raise ValueError("execution plan is missing")
                result = execute_signature_plan(
                    self.request.plan,
                    adapter,  # type: ignore[arg-type]
                    cancellation_token=self.request.cancellation_token,
                    event_sink=self._emit_event,
                )
                return _TerminalOutcome("completed", result)
            raise ValueError("unknown worker operation")
        except Exception as error:
            return self._failure_outcome(error)
        finally:
            # CPython releases ordinary adapter references when this helper exits.
            # No process-wide collection is used to manufacture COM ordering.
            adapter = None

    def _emit_terminal(self, outcome: _TerminalOutcome) -> None:
        if outcome.kind == "completed":
            self.completed.emit(outcome.payload)
        elif outcome.kind == "environment_ready":
            self.environment_ready.emit(outcome.payload)
        else:
            code, message = outcome.payload  # type: ignore[misc]
            self.failed.emit(str(code), str(message))

    @Slot()
    def run(self) -> None:
        runtime: ComRuntime | None = None
        initialized = False
        outcome: _TerminalOutcome | None = None
        try:
            runtime = self._com_runtime_factory()
            runtime.CoInitialize()
            initialized = True
            outcome = self._operation_outcome()
        except Exception as error:
            outcome = self._failure_outcome(error)

        cleanup_failed = False
        if initialized and runtime is not None:
            try:
                runtime.CoUninitialize()
            except Exception:
                cleanup_failed = True

        if cleanup_failed:
            if outcome is not None and outcome.kind == "failed":
                primary_code, _message = outcome.payload  # type: ignore[misc]
                outcome = _TerminalOutcome(
                    "failed",
                    (
                        f"{primary_code}_COM_CLEANUP_FAILED",
                        "Photoshop workflow and COM cleanup failed",
                    ),
                )
            else:
                outcome = _TerminalOutcome(
                    "failed",
                    ("COM_CLEANUP_FAILED", "Photoshop workflow cleanup failed"),
                )

        if outcome is None:
            outcome = _TerminalOutcome(
                "failed",
                ("WORKER_TERMINAL_MISSING", "Photoshop workflow failed"),
            )
        try:
            self._emit_terminal(outcome)
        finally:
            self.finished.emit()


class RunningJob(QObject):
    """Own a QThread without exposing any adapter or COM object."""

    event = Signal(object)
    completed = Signal(object)
    environment_ready = Signal(object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        request: WorkerRequest,
        *,
        adapter_factory: AdapterFactory = PhotoshopAdapter,
        com_runtime_factory: ComRuntimeFactory = _default_com_runtime,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.request = request
        self.thread = QThread()
        self.worker = WorkflowWorker(
            request,
            adapter_factory=adapter_factory,
            com_runtime_factory=com_runtime_factory,
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.event.connect(self.event.emit)
        self.worker.completed.connect(self.completed.emit)
        self.worker.environment_ready.connect(self.environment_ready.emit)
        self.worker.failed.connect(self.failed.emit)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finished.emit)
        self.thread.finished.connect(self.thread.deleteLater)

    def start(self) -> None:
        self.thread.start()

    def cancel(self) -> None:
        self.request.cancellation_token.cancel()

    def is_running(self) -> bool:
        try:
            return self.thread.isRunning()
        except RuntimeError:
            return False

    def wait(self, milliseconds: int = -1) -> bool:
        try:
            if milliseconds < 0:
                return self.thread.wait()
            return self.thread.wait(milliseconds)
        except RuntimeError:
            return True

JobFactory = Callable[[WorkerRequest], RunningJob]


def create_job(request: WorkerRequest) -> RunningJob:
    return RunningJob(request)

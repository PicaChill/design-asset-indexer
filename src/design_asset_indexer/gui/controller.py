"""State controller for the Qt GUI.

The controller owns immutable workflow inputs and plans.  It deliberately has no
Photoshop adapter reference: adapters are created and destroyed by the worker
that executes one workflow phase.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from PySide6.QtCore import QObject, Signal

from ..workflow_models import (
    CancellationToken,
    ExecutionRunResult,
    InspectRunResult,
    PlanRunResult,
    SignatureExecutionPlan,
    SignatureRule,
    WorkflowEvent,
    WorkflowOptions,
)
from .workers import (
    EnvironmentCheckResult,
    JobFactory,
    RunningJob,
    WorkerOperation,
    WorkerRequest,
    create_job,
)


class GuiState(str, Enum):
    SETUP = "SETUP"
    INSPECTING = "INSPECTING"
    INSPECTED = "INSPECTED"
    PLANNING = "PLANNING"
    DRY_RUN_REVIEW = "DRY_RUN_REVIEW"
    EXECUTING = "EXECUTING"
    RESULT = "RESULT"


class WorkflowController(QObject):
    state_changed = Signal(object)
    busy_changed = Signal(bool, str)
    environment_ready = Signal(object)
    inspect_ready = Signal(object)
    plan_ready = Signal(object)
    execution_ready = Signal(object)
    event_received = Signal(object)
    failed = Signal(str, str)
    job_finished = Signal()

    def __init__(
        self,
        *,
        job_factory: JobFactory = create_job,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._job_factory = job_factory
        self.state = GuiState.SETUP
        self.options: WorkflowOptions | None = None
        self.rule: SignatureRule | None = None
        self.inspect_result: InspectRunResult | None = None
        self.plan_result: PlanRunResult | None = None
        self.plan: SignatureExecutionPlan | None = None
        self.execution_result: ExecutionRunResult | None = None
        self._job: RunningJob | None = None
        self._operation: WorkerOperation | None = None

    @property
    def busy(self) -> bool:
        return self._job is not None and self._job.is_running()

    @staticmethod
    def make_options(
        input_text: str,
        output_text: str,
        *,
        recursive: bool,
        include: str,
        max_files: int,
    ) -> WorkflowOptions:
        source = Path(input_text.strip()).expanduser()
        destination = Path(output_text.strip()).expanduser()
        if not input_text.strip() or not output_text.strip():
            raise ValueError("请选择输入目录和独立输出目录。")
        if not source.exists() or not source.is_dir():
            raise ValueError("输入目录不存在或不是文件夹。")
        if not include.strip():
            raise ValueError("文件匹配规则不能为空。")
        if max_files < 1:
            raise ValueError("最大文件数必须大于 0。")
        source_resolved = source.resolve()
        destination_resolved = destination.resolve()
        if (
            source_resolved == destination_resolved
            or source_resolved in destination_resolved.parents
            or destination_resolved in source_resolved.parents
        ):
            raise ValueError("输入与输出必须是互不包含的独立目录。")
        return WorkflowOptions(
            input_dir=source_resolved,
            output_dir=destination_resolved,
            recursive=recursive,
            include=include.strip(),
            max_files=max_files,
        )

    def _set_state(self, state: GuiState) -> None:
        self.state = state
        self.state_changed.emit(state)

    def invalidate_setup(self) -> None:
        if self.busy:
            return
        self.options = None
        self.rule = None
        self.inspect_result = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._set_state(GuiState.SETUP)

    def invalidate_rule(self) -> None:
        if self.busy:
            return
        self.rule = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._set_state(
            GuiState.INSPECTED if self.inspect_result is not None else GuiState.SETUP
        )

    def check_environment(self) -> None:
        self._start(
            WorkerRequest(WorkerOperation.ENVIRONMENT, CancellationToken()),
            GuiState.SETUP,
            "正在检查 Photoshop…",
        )

    def start_inspect(self, options: WorkflowOptions) -> None:
        self.options = options
        self.rule = None
        self.inspect_result = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._start(
            WorkerRequest(
                WorkerOperation.INSPECT,
                CancellationToken(),
                options=options,
            ),
            GuiState.INSPECTING,
            "正在检查 PSD 文字图层…",
        )

    def start_plan(self, rule: SignatureRule) -> None:
        if self.options is None or self.inspect_result is None:
            raise RuntimeError("请先完成检查。")
        self.rule = rule
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._start(
            WorkerRequest(
                WorkerOperation.PLAN,
                CancellationToken(),
                options=self.options,
                rule=rule,
            ),
            GuiState.PLANNING,
            "正在生成只读预演计划…",
        )

    def start_execute(self) -> None:
        if self.plan is None:
            raise RuntimeError("没有可执行的已确认计划。")
        # The frozen plan is the only execution input.  No UI parameter is rebuilt.
        self._start(
            WorkerRequest(
                WorkerOperation.EXECUTE,
                CancellationToken(),
                plan=self.plan,
            ),
            GuiState.EXECUTING,
            "正在按已确认计划处理输出副本…",
        )

    def cancel(self) -> None:
        if self._job is not None:
            self._job.cancel()

    def _start(
        self,
        request: WorkerRequest,
        state: GuiState,
        label: str,
    ) -> None:
        if self.busy:
            raise RuntimeError("已有任务正在运行。")
        job = self._job_factory(request)
        self._job = job
        self._operation = request.operation
        job.event.connect(self.event_received.emit)
        job.completed.connect(self._on_completed)
        job.environment_ready.connect(self._on_environment)
        job.failed.connect(self._on_failed)
        job.finished.connect(self._on_finished)
        self._set_state(state)
        self.busy_changed.emit(True, label)
        job.start()

    def _on_environment(self, result: EnvironmentCheckResult) -> None:
        self.environment_ready.emit(result)

    def _on_failed(self, code: str, message: str) -> None:
        operation = self._operation
        if operation is WorkerOperation.ENVIRONMENT:
            self.environment_ready.emit(
                EnvironmentCheckResult(False, None, code, message)
            )
        elif operation is WorkerOperation.INSPECT:
            self._set_state(GuiState.SETUP)
        elif operation is WorkerOperation.PLAN:
            self._set_state(GuiState.INSPECTED)
        elif operation is WorkerOperation.EXECUTE:
            self._set_state(GuiState.DRY_RUN_REVIEW)
        self.failed.emit(code, message)

    def _on_completed(self, result: object) -> None:
        operation = self._operation
        if operation is WorkerOperation.INSPECT and isinstance(result, InspectRunResult):
            self.inspect_result = result
            self._set_state(GuiState.INSPECTED)
            self.inspect_ready.emit(result)
        elif operation is WorkerOperation.PLAN and isinstance(result, PlanRunResult):
            self.plan_result = result
            self.plan = result.plan
            self._set_state(GuiState.DRY_RUN_REVIEW)
            self.plan_ready.emit(result)
        elif operation is WorkerOperation.EXECUTE and isinstance(
            result, ExecutionRunResult
        ):
            self.execution_result = result
            self._set_state(GuiState.RESULT)
            self.execution_ready.emit(result)

    def _on_finished(self) -> None:
        self._job = None
        self._operation = None
        self.busy_changed.emit(False, "")
        self.job_finished.emit()

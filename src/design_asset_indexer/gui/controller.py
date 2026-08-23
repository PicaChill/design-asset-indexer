"""State controller for the Qt GUI.

The controller owns immutable workflow inputs and plans.  It deliberately has no
Photoshop adapter reference: adapters are created and destroyed by the worker
that executes one workflow phase.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    USER_CONFIRMED = "USER_CONFIRMED"
    EXECUTING = "EXECUTING"
    RESULT = "RESULT"


@dataclass(frozen=True)
class ReportReference:
    phase: str
    plan_id: str
    output_dir: Path
    summary_path: Path
    run_generation: int


@dataclass(frozen=True)
class _PlanConfirmation:
    plan: SignatureExecutionPlan
    plan_generation: int
    plan_id: str
    review_acknowledged: bool
    partial_acknowledged: bool


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
        self.dry_run_report_ref: ReportReference | None = None
        self.formal_report_ref: ReportReference | None = None
        self._plan_generation = 0
        self._execution_generation = 0
        self._confirmation: _PlanConfirmation | None = None
        self._starting = False
        self._job: RunningJob | None = None
        self._operation: WorkerOperation | None = None

    @property
    def busy(self) -> bool:
        return self._starting or self._job is not None

    def _require_idle(self) -> None:
        if self.busy:
            raise RuntimeError("已有任务正在运行。")

    @property
    def plan_generation(self) -> int:
        return self._plan_generation

    @property
    def current_plan_confirmed(self) -> bool:
        confirmation = self._confirmation
        return (
            self.state is GuiState.USER_CONFIRMED
            and confirmation is not None
            and self.plan is confirmation.plan
            and self._plan_generation == confirmation.plan_generation
            and self.plan is not None
            and self.plan.plan_id == confirmation.plan_id
        )

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

    def _clear_confirmation(self) -> None:
        self._confirmation = None

    def _clear_report_authority(self) -> None:
        self.dry_run_report_ref = None
        self.formal_report_ref = None

    def _fail_closed_execute(self) -> None:
        self._clear_confirmation()
        self.rule = None
        self.inspect_result = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._clear_report_authority()
        self._set_state(GuiState.SETUP)

    def invalidate_setup(self) -> None:
        if self.busy:
            return
        self.options = None
        self.rule = None
        self.inspect_result = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._clear_confirmation()
        self._clear_report_authority()
        self._set_state(GuiState.SETUP)

    def invalidate_rule(self) -> None:
        if self.busy:
            return
        self.rule = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._clear_confirmation()
        self._clear_report_authority()
        self._set_state(
            GuiState.INSPECTED if self.inspect_result is not None else GuiState.SETUP
        )

    def check_environment(self) -> None:
        self._require_idle()
        self._start(
            WorkerRequest(WorkerOperation.ENVIRONMENT, CancellationToken()),
            GuiState.SETUP,
            "正在检查 Photoshop…",
        )

    def start_inspect(self, options: WorkflowOptions) -> None:
        self._require_idle()
        self.options = options
        self.rule = None
        self.inspect_result = None
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._clear_confirmation()
        self._clear_report_authority()
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
        self._require_idle()
        if (
            self.state is not GuiState.INSPECTED
            or self.options is None
            or self.inspect_result is None
        ):
            raise RuntimeError("请先完成检查。")
        if not self.inspect_result.planned_items_complete:
            raise RuntimeError(
                "检查未完成，不能基于半份检查结果生成正式预演；请重新检查。"
            )
        self.rule = rule
        self.plan_result = None
        self.plan = None
        self.execution_result = None
        self._clear_confirmation()
        self._clear_report_authority()
        self._plan_generation += 1
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

    def confirm_current_plan(
        self,
        *,
        expected_plan: SignatureExecutionPlan,
        expected_plan_id: str,
        expected_generation: int,
        review_acknowledged: bool,
        partial_acknowledged: bool,
    ) -> None:
        result = self.plan_result
        plan = self.plan
        if self.state is not GuiState.DRY_RUN_REVIEW:
            raise RuntimeError("当前不处于可确认的预演状态。")
        if plan is None or result is None or result.plan is not plan:
            raise RuntimeError("当前预演计划已失效，请重新生成 dry-run。")
        if not result.planned_items_complete:
            raise RuntimeError("预演未完整完成，不能确认执行。")
        if expected_plan is not plan or expected_generation != self._plan_generation:
            raise RuntimeError("确认期间计划已被替换，请重新核对。")
        if expected_plan_id != plan.plan_id:
            raise RuntimeError("确认的计划编号与当前计划不一致。")
        if not review_acknowledged:
            raise RuntimeError("请先完成全部执行前确认。")
        if result.partial_plan and not partial_acknowledged:
            raise RuntimeError("部分计划必须单独确认未纳入项。")
        self._confirmation = _PlanConfirmation(
            plan=plan,
            plan_generation=self._plan_generation,
            plan_id=plan.plan_id,
            review_acknowledged=True,
            partial_acknowledged=partial_acknowledged,
        )
        self._set_state(GuiState.USER_CONFIRMED)

    def revoke_confirmation(self) -> None:
        self._clear_confirmation()
        if self.state is GuiState.USER_CONFIRMED:
            self._set_state(
                GuiState.DRY_RUN_REVIEW if self.plan is not None else GuiState.SETUP
            )

    def start_execute(self) -> None:
        self._require_idle()
        if self.state is not GuiState.USER_CONFIRMED or self.plan is None:
            raise RuntimeError("没有可执行的已确认计划。")
        if not self.current_plan_confirmed:
            self.revoke_confirmation()
            raise RuntimeError("当前确认与计划不一致，请重新核对 dry-run。")
        self.execution_result = None
        self.formal_report_ref = None
        self._execution_generation += 1
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
        self._require_idle()
        self._starting = True
        try:
            job = self._job_factory(request)
        except Exception:
            try:
                self._handle_start_failure(request.operation)
            finally:
                self._starting = False
            raise RuntimeError("后台任务创建失败，状态已安全重置。") from None
        self._job = job
        self._operation = request.operation
        busy_announced = False
        try:
            job.event.connect(self.event_received.emit)
            job.completed.connect(self._on_completed)
            job.environment_ready.connect(self._on_environment)
            job.failed.connect(self._on_failed)
            job.finished.connect(lambda current=job: self._on_finished(current))
            self._set_state(state)
            busy_announced = True
            self.busy_changed.emit(True, label)
            job.start()
        except Exception:
            self._job = None
            self._operation = None
            try:
                self._handle_start_failure(request.operation)
            finally:
                self._starting = False
                if busy_announced:
                    self.busy_changed.emit(False, "")
            raise RuntimeError("后台任务启动失败，状态已安全重置。") from None
        self._starting = False

    def _handle_start_failure(self, operation: WorkerOperation) -> None:
        if operation is WorkerOperation.EXECUTE:
            self._fail_closed_execute()
        elif operation is WorkerOperation.INSPECT:
            self.inspect_result = None
            self.plan_result = None
            self.plan = None
            self._clear_confirmation()
            self._clear_report_authority()
            self._set_state(GuiState.SETUP)
        elif operation is WorkerOperation.PLAN:
            self.plan_result = None
            self.plan = None
            self.execution_result = None
            self._clear_confirmation()
            self._clear_report_authority()
            self._set_state(
                GuiState.INSPECTED
                if self.inspect_result is not None
                and self.inspect_result.planned_items_complete
                else GuiState.SETUP
            )
        else:
            self._set_state(GuiState.SETUP)

    def _on_environment(self, result: EnvironmentCheckResult) -> None:
        self.environment_ready.emit(result)

    def _on_failed(self, code: str, message: str) -> None:
        operation = self._operation
        if operation is WorkerOperation.ENVIRONMENT:
            self.environment_ready.emit(
                EnvironmentCheckResult(False, None, code, message)
            )
        elif operation is WorkerOperation.INSPECT:
            self.inspect_result = None
            self._set_state(GuiState.SETUP)
        elif operation is WorkerOperation.PLAN:
            self.plan_result = None
            self.plan = None
            self._clear_confirmation()
            self.dry_run_report_ref = None
            self._set_state(
                GuiState.INSPECTED
                if self.inspect_result is not None
                and self.inspect_result.planned_items_complete
                else GuiState.SETUP
            )
        elif operation is WorkerOperation.EXECUTE:
            self._fail_closed_execute()
        self.failed.emit(code, message)

    def _on_completed(self, result: object) -> None:
        operation = self._operation
        if operation is WorkerOperation.INSPECT and isinstance(result, InspectRunResult):
            self.inspect_result = result
            self._set_state(GuiState.INSPECTED)
            self.inspect_ready.emit(result)
        elif operation is WorkerOperation.PLAN and isinstance(result, PlanRunResult):
            self.plan_result = result
            self.plan = result.plan if result.planned_items_complete else None
            self._clear_confirmation()
            self.formal_report_ref = None
            if self.plan is not None:
                self.dry_run_report_ref = ReportReference(
                    phase="DRY_RUN",
                    plan_id=self.plan.plan_id,
                    output_dir=self.plan.options.output_dir,
                    summary_path=self.plan.options.output_dir / "summary.json",
                    run_generation=self._plan_generation,
                )
            else:
                self.dry_run_report_ref = None
            self._set_state(GuiState.DRY_RUN_REVIEW)
            self.plan_ready.emit(result)
        elif operation is WorkerOperation.EXECUTE and isinstance(
            result, ExecutionRunResult
        ):
            self.execution_result = result
            self._clear_confirmation()
            if result.reports_written and self.plan is not None:
                self.formal_report_ref = ReportReference(
                    phase="EXECUTION",
                    plan_id=result.plan_id,
                    output_dir=self.plan.options.output_dir,
                    summary_path=self.plan.options.output_dir / "summary.json",
                    run_generation=self._execution_generation,
                )
            else:
                self.formal_report_ref = None
            if result.stale:
                self.plan_result = None
                self.plan = None
            self._set_state(GuiState.RESULT)
            self.execution_ready.emit(result)

    def _on_finished(self, finished_job: RunningJob) -> None:
        wait = getattr(finished_job, "wait", None)
        if callable(wait):
            wait()
        if self._job is not finished_job:
            return
        self._starting = False
        self._job = None
        self._operation = None
        self.busy_changed.emit(False, "")
        self.job_finished.emit()

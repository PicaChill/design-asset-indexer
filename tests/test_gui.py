from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QDialog

from design_asset_indexer.gui.controller import (
    GuiState,
    ReportReference,
    WorkflowController,
)
from design_asset_indexer.gui.main_window import MainWindow
from design_asset_indexer.gui.workers import WorkerOperation, WorkerRequest
from design_asset_indexer.workflow_models import (
    ExecutionItemResult,
    ExecutionRunResult,
    InspectItem,
    InspectRunResult,
    OutputSnapshot,
    PlanItem,
    PlanRunResult,
    SignatureExecutionPlan,
    SignatureRule,
    SourceSnapshot,
    WorkflowOptions,
    freeze_summary,
)


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application


class FakeJob(QObject):
    event = Signal(object)
    completed = Signal(object)
    environment_ready = Signal(object)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(self, request: WorkerRequest) -> None:
        super().__init__()
        self.request = request
        self.running = False
        self.wait_calls = 0

    def start(self) -> None:
        self.running = True

    def is_running(self) -> bool:
        return self.running

    def wait(self, _milliseconds: int = -1) -> bool:
        self.wait_calls += 1
        return True

    def cancel(self) -> None:
        self.request.cancellation_token.cancel()

    def complete(self, result: object) -> None:
        self.completed.emit(result)
        self.running = False
        self.finished.emit()

    def fail(self, code: str = "WORKER_FAILED", message: str = "safe failure") -> None:
        self.failed.emit(code, message)
        self.running = False
        self.finished.emit()


class JobRecorder:
    def __init__(self) -> None:
        self.jobs: list[FakeJob] = []

    def __call__(self, request: WorkerRequest) -> FakeJob:
        job = FakeJob(request)
        self.jobs.append(job)
        return job


def _options(source: Path, output: Path, *, max_files: int = 100) -> WorkflowOptions:
    source.mkdir(parents=True, exist_ok=True)
    return WorkflowOptions(source, output, recursive=True, max_files=max_files)


def _inspect(*, partial: bool = False) -> InspectRunResult:
    item = InspectItem(
        "folder/sample.psd",
        True,
        "Group/Signature",
        "Signature",
        "TEXT",
        "OLD_TEXT",
        False,
        "",
    )
    return InspectRunResult(
        (item,),
        freeze_summary({"file_count": 1, "max_files_reached": partial}),
        1,
        0,
        False,
        False,
        partial,
        2 if partial else 1,
        1,
    )


def _plan(options: WorkflowOptions, *, partial: bool = False) -> SignatureExecutionPlan:
    item = PlanItem("folder/sample.psd", "WOULD_REPLACE", 1, "folder/sample.psd")
    return SignatureExecutionPlan(
        "a" * 64,
        "2026-08-23T00:00:00Z",
        options,
        SignatureRule("OLD_TEXT", "NEW_TEXT", "Signature"),
        ("folder/sample.psd", "extra.psd") if partial else ("folder/sample.psd",),
        (SourceSnapshot("folder/sample.psd", 10, 20),),
        (OutputSnapshot("folder/sample.psd", False, False, None, None),),
        (item,),
        partial,
    )


def _plan_result(plan: SignatureExecutionPlan) -> PlanRunResult:
    return PlanRunResult(
        plan,
        plan.items,
        freeze_summary(
            {
                "file_count": 1,
                "status_counts": {"WOULD_REPLACE": 1},
                "max_files_reached": plan.max_files_reached,
                "dry_run": True,
            }
        ),
        1,
        0,
        False,
        False,
        plan.max_files_reached,
        plan.candidate_count,
        plan.selected_count,
    )


def _execution(plan: SignatureExecutionPlan, **changes) -> ExecutionRunResult:
    values = {
        "plan_id": plan.plan_id,
        "items": (
            ExecutionItemResult(
                "folder/private-name.psd", "REPLACED", 1, 1, "folder/private-name.psd"
            ),
        ),
        "summary": freeze_summary(
            {"file_count": 1, "status_counts": {"REPLACED": 1}}
        ),
        "processed_count": 1,
        "remaining_count": 0,
        "cancelled": False,
        "stale": False,
        "max_files_reached": False,
        "candidate_count": 1,
        "selected_count": 1,
        "workflow_status": "RESULT",
        "reports_written": True,
    }
    values.update(changes)
    return ExecutionRunResult(**values)


def _prime_review(
    controller: WorkflowController,
    plan: SignatureExecutionPlan,
    *,
    generation: int = 1,
) -> None:
    controller.options = plan.options
    controller.inspect_result = _inspect(partial=plan.partial_plan)
    controller.plan = plan
    controller.plan_result = _plan_result(plan)
    controller._plan_generation = generation
    controller._set_state(GuiState.DRY_RUN_REVIEW)


def _confirm(controller: WorkflowController) -> None:
    assert controller.plan is not None
    result = controller.plan_result
    assert result is not None
    controller.confirm_current_plan(
        expected_plan=controller.plan,
        expected_plan_id=controller.plan.plan_id,
        expected_generation=controller.plan_generation,
        review_acknowledged=True,
        partial_acknowledged=result.partial_plan,
    )


def test_app_shell_has_five_non_clickable_steps(qapp):
    window = MainWindow(auto_environment_check=False)
    assert window.pages.count() == 5
    assert len(window.step_buttons) == 5
    assert all(not button.isEnabled() for button in window.step_buttons)
    assert "PSD" in window.windowTitle()
    window.close()


def test_setup_validation_rejects_missing_nested_and_same_paths(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="输入目录"):
        WorkflowController.make_options(
            str(tmp_path / "missing"), str(tmp_path / "output"),
            recursive=False, include="*.psd", max_files=100,
        )
    for output in (source, source / "output"):
        with pytest.raises(ValueError, match="独立目录"):
            WorkflowController.make_options(
                str(source), str(output),
                recursive=False, include="*.psd", max_files=100,
            )


def test_parameter_change_invalidates_plan(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    controller.inspect_result = _inspect()
    controller.plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    controller.plan_result = _plan_result(controller.plan)
    controller.invalidate_rule()
    assert controller.state is GuiState.INSPECTED
    assert controller.plan is None
    controller.invalidate_setup()
    assert controller.state is GuiState.SETUP
    assert controller.inspect_result is None


def test_select_inspect_row_prefills_old_text(qapp):
    window = MainWindow(auto_environment_check=False)
    window.show_inspect_result(_inspect())
    proxy_index = window.inspect_proxy.index(0, 0)
    window._select_inspect_row(proxy_index)
    assert window.from_edit.text() == "OLD_TEXT"
    assert window.selected_layer_name == "Signature"
    assert window.any_layer_radio.isChecked()
    window.close()


def test_partial_inspect_shows_banner(qapp):
    window = MainWindow(auto_environment_check=False)
    window.show_inspect_result(_inspect(partial=True))
    text = window.inspect_summary.label.text()
    assert "未纳入" in text
    assert "完成" not in text
    window.close()


def test_partial_plan_requires_explicit_extra_confirmation(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"), partial=True)
    _prime_review(controller, plan)
    window.show_plan_result(controller.plan_result)
    for checkbox in window.confirm_checks:
        checkbox.setChecked(True)
    assert window.partial_confirm.isVisible() is False or not window.execute_button.isEnabled()
    window.partial_confirm.setChecked(True)
    assert window.execute_button.isEnabled()
    window.close()


def test_execute_passes_exact_plan_object(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    controller.start_execute()
    request = recorder.jobs[-1].request
    assert request.plan is plan
    assert request.options is None
    assert request.rule is None
    controller.cancel()
    assert request.cancellation_token.cancelled


def test_result_distinguishes_cancelled_stale_and_partial(qapp, tmp_path):
    window = MainWindow(auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    window.show_execution_result(
        _execution(plan, cancelled=True, processed_count=0, remaining_count=1)
    )
    assert "取消" in window.result_title.text()
    window.show_execution_result(
        _execution(plan, stale=True, processed_count=0, remaining_count=1)
    )
    assert "过期" in window.result_title.text()
    window.close()


def test_public_diagnostic_copy_is_redacted(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "private-source", tmp_path / "private-output"))
    controller.execution_result = _execution(plan)
    window._copy_diagnostic()
    copied = QApplication.clipboard().text()
    parsed = json.loads(copied)
    assert parsed["phase"] == "RESULT"
    assert "private-name.psd" not in copied
    assert str(tmp_path) not in copied
    assert "OLD_TEXT" not in copied
    window.close()


def test_base_gui_package_import_does_not_connect_photoshop(qapp):
    import design_asset_indexer.gui as gui

    assert "pip install" in gui.GUI_EXTRA_HINT


def test_gui_starts_offscreen(qapp):
    window = MainWindow(auto_environment_check=False)
    window.show()
    qapp.processEvents()
    assert window.isVisible()
    window.close()


def test_initial_state_setup(qapp):
    window = MainWindow(auto_environment_check=False)
    assert window.controller.state is GuiState.SETUP
    assert window.pages.currentIndex() == 0
    window.close()


def test_steps_locked_initially(qapp):
    window = MainWindow(auto_environment_check=False)
    assert not any(button.isEnabled() for button in window.step_buttons)
    window.close()


def test_input_output_overlap_blocks_inspect(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError):
        WorkflowController.make_options(
            str(source), str(source / "output"),
            recursive=False, include="*.psd", max_files=100,
        )


def test_missing_input_blocks_inspect(tmp_path):
    with pytest.raises(ValueError):
        WorkflowController.make_options(
            str(tmp_path / "missing"), str(tmp_path / "output"),
            recursive=False, include="*.psd", max_files=100,
        )


def test_invalid_max_files_blocks_inspect(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError):
        WorkflowController.make_options(
            str(source), str(tmp_path / "output"),
            recursive=False, include="*.psd", max_files=0,
        )


def test_inspect_result_populates_table(qapp):
    window = MainWindow(auto_environment_check=False)
    window.show_inspect_result(_inspect())
    assert window.inspect_model.rowCount() == 1
    window.close()


def test_multiple_layer_names_show_role_warning(qapp):
    window = MainWindow(auto_environment_check=False)
    result = _inspect()
    second = replace(
        result.items[0],
        layer_path="Other/Copy",
        layer_name="Copy",
    )
    window.inspect_model.set_items((*result.items, second))
    window._select_inspect_row(window.inspect_proxy.index(0, 0))
    assert "多个图层" in window.role_warning.label.text()
    window.close()


def test_plan_required_before_execute(qapp):
    controller = WorkflowController(job_factory=JobRecorder())
    with pytest.raises(RuntimeError, match="计划"):
        controller.start_execute()


def test_plan_cards_map_decisions(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    controller.plan = plan
    controller.plan_result = _plan_result(plan)
    window.show_plan_result(controller.plan_result)
    assert window.plan_cards["WOULD_REPLACE"].value_label.text() == "1"
    window.close()


def test_execute_does_not_reconstruct_rule(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    controller.start_execute()
    assert recorder.jobs[-1].request.rule is None


def test_cancel_requests_token_only(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    options = _options(tmp_path / "source", tmp_path / "output")
    controller.start_inspect(options)
    controller.cancel()
    assert recorder.jobs[-1].request.cancellation_token.cancelled


def test_stale_result_blocks_continue(qapp, tmp_path):
    window = MainWindow(auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    window.show_execution_result(_execution(plan, stale=True, remaining_count=1))
    assert "安全停止" in window.result_title.text()
    assert window.pages.currentIndex() == 4
    window.close()


def test_result_title_complete(qapp, tmp_path):
    window = MainWindow(auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    window.show_execution_result(_execution(plan))
    assert window.result_title.text() == "任务完成"
    window.close()


def test_result_title_partial(qapp, tmp_path):
    window = MainWindow(auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"), partial=True)
    result = _execution(
        plan,
        max_files_reached=True,
        candidate_count=2,
        selected_count=1,
    )
    window.show_execution_result(result)
    assert "未纳入" in window.result_title.text()
    window.close()


def test_result_title_cancelled(qapp, tmp_path):
    window = MainWindow(auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    window.show_execution_result(_execution(plan, cancelled=True, remaining_count=1))
    assert "取消" in window.result_title.text()
    window.close()


def test_plan_without_controller_confirmation_cannot_execute(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    with pytest.raises(RuntimeError, match="确认"):
        controller.start_execute()


def test_confirm_current_plan_enters_user_confirmed(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    assert controller.state is GuiState.USER_CONFIRMED
    assert controller.current_plan_confirmed


def test_same_plan_id_replan_invalidates_confirmation(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    first = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, first)
    _confirm(controller)
    second = replace(first, created_at="2026-08-23T00:00:01Z")
    assert second.plan_id == first.plan_id
    assert second is not first
    controller._plan_generation += 1
    controller._operation = WorkerOperation.PLAN
    controller._on_completed(_plan_result(second))
    assert controller.state is GuiState.DRY_RUN_REVIEW
    assert not controller.current_plan_confirmed
    with pytest.raises(RuntimeError, match="确认"):
        controller.start_execute()


def test_confirm_rejects_wrong_plan_identity_id_or_generation(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan, generation=7)
    other = replace(plan, created_at="later")
    with pytest.raises(RuntimeError, match="替换"):
        controller.confirm_current_plan(
            expected_plan=other,
            expected_plan_id=plan.plan_id,
            expected_generation=7,
            review_acknowledged=True,
            partial_acknowledged=False,
        )
    with pytest.raises(RuntimeError, match="替换"):
        controller.confirm_current_plan(
            expected_plan=plan,
            expected_plan_id=plan.plan_id,
            expected_generation=6,
            review_acknowledged=True,
            partial_acknowledged=False,
        )
    with pytest.raises(RuntimeError, match="编号"):
        controller.confirm_current_plan(
            expected_plan=plan,
            expected_plan_id="different",
            expected_generation=7,
            review_acknowledged=True,
            partial_acknowledged=False,
        )


@pytest.mark.parametrize("invalidation", ("setup", "rule"))
def test_parameter_or_rule_change_invalidates_confirmation(
    qapp, tmp_path, invalidation
):
    controller = WorkflowController(job_factory=JobRecorder())
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    getattr(controller, f"invalidate_{invalidation}")()
    assert not controller.current_plan_confirmed
    assert controller.plan is None


def test_cancelled_or_stale_inspect_cannot_plan(qapp, tmp_path):
    for result in (
        replace(_inspect(), cancelled=True, processed_count=0, remaining_count=1),
        replace(_inspect(), stale=True, processed_count=0, remaining_count=1),
    ):
        controller = WorkflowController(job_factory=JobRecorder())
        controller.options = _options(tmp_path / "source", tmp_path / "output")
        controller.inspect_result = result
        controller._set_state(GuiState.INSPECTED)
        with pytest.raises(RuntimeError, match="检查未完成"):
            controller.start_plan(SignatureRule("OLD_TEXT", "NEW_TEXT"))


def test_max_files_partial_complete_inspect_can_plan(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    controller.options = _options(tmp_path / "source", tmp_path / "output")
    controller.inspect_result = _inspect(partial=True)
    controller._set_state(GuiState.INSPECTED)
    controller.start_plan(SignatureRule("OLD_TEXT", "NEW_TEXT"))
    assert controller.state is GuiState.PLANNING
    assert recorder.jobs[-1].request.operation is WorkerOperation.PLAN


def test_execute_worker_failure_drops_plan_and_requires_reinspect(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    controller.start_execute()
    controller.execution_result = _execution(plan)
    controller.formal_report_ref = ReportReference(
        "EXECUTION", plan.plan_id, plan.options.output_dir,
        plan.options.output_dir / "summary.json", 1,
    )
    recorder.jobs[-1].fail("UNEXPECTED", "safe failure")
    assert controller.state is GuiState.SETUP
    assert controller.inspect_result is None
    assert controller.plan is None
    assert controller.execution_result is None
    assert controller.formal_report_ref is None
    assert not controller.current_plan_confirmed


def test_execute_job_start_exception_is_transactional_and_fail_closed(qapp, tmp_path):
    class StartFailureJob(FakeJob):
        def start(self) -> None:
            raise RuntimeError("private startup detail")

    controller = WorkflowController(job_factory=StartFailureJob)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    with pytest.raises(RuntimeError, match="安全重置"):
        controller.start_execute()
    assert controller.state is GuiState.SETUP
    assert controller.plan is None
    assert controller.execution_result is None
    assert not controller.busy


def test_finished_job_is_joined_before_controller_releases_it(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    controller.start_inspect(_options(tmp_path / "source", tmp_path / "output"))
    job = recorder.jobs[-1]

    job.complete(_inspect())

    assert job.wait_calls == 1
    assert controller._job is None
    assert not controller.busy


def test_exact_layer_scope_is_visible_in_inspect_and_review(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    window.inspect_model.set_items(_inspect().items)
    window._select_inspect_row(window.inspect_proxy.index(0, 0))
    assert window.layer_scope_label.text() == "不限图层名"
    window.exact_layer_radio.setChecked(True)
    assert "Signature" in window.layer_scope_label.text()
    assert window.layer_scope_label.toolTip() == window.layer_scope_label.text()
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    window.show_plan_result(controller.plan_result)
    assert "Signature" in window.review_layer_scope.label.text()
    window.close()


def test_same_text_different_layer_selection_invalidates_confirmed_plan(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    first = _inspect().items[0]
    second = replace(first, layer_name="Other", layer_path="Group/Other")
    window.inspect_model.set_items((first, second))
    window._select_inspect_row(window.inspect_proxy.index(0, 0))
    window.exact_layer_radio.setChecked(True)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    window._select_inspect_row(window.inspect_proxy.index(1, 0))
    assert controller.plan is None
    assert not controller.current_plan_confirmed
    assert window.selected_layer_name == "Other"
    window.close()


def test_new_task_clears_layer_scope_and_exact_mode(qapp):
    window = MainWindow(auto_environment_check=False)
    window.inspect_model.set_items(_inspect().items)
    window._select_inspect_row(window.inspect_proxy.index(0, 0))
    window.exact_layer_radio.setChecked(True)
    window._new_task()
    assert window.selected_layer_name == ""
    assert window.any_layer_radio.isChecked()
    assert not window.exact_layer_radio.isEnabled()
    assert window.layer_scope_label.text() == "不限图层名"
    window.close()


def test_new_inspect_clears_layer_scope_and_exact_mode(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = MainWindow(controller=controller, auto_environment_check=False)
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    window.input_picker.set_path(str(source))
    window.output_picker.set_path(str(output))
    window.inspect_model.set_items(_inspect().items)
    window._select_inspect_row(window.inspect_proxy.index(0, 0))
    window.exact_layer_radio.setChecked(True)

    window._start_inspect()

    assert window.selected_layer_name == ""
    assert window.any_layer_radio.isChecked()
    assert not window.exact_layer_radio.isEnabled()
    assert window.layer_scope_label.text() == "不限图层名"
    recorder.jobs[-1].complete(_inspect())
    window.close()


def test_cancelled_inspect_guidance_blocks_plan_button(qapp):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    result = replace(
        _inspect(),
        cancelled=True,
        processed_count=0,
        remaining_count=1,
    )
    controller.inspect_result = result

    window.show_inspect_result(result)

    assert "检查未完成" in window.inspect_summary.label.text()
    assert not window.plan_button.isEnabled()
    window.close()


def test_partial_plan_banner_remains_visible(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"), partial=True)
    _prime_review(controller, plan)

    window.show_plan_result(controller.plan_result)
    for checkbox in window.confirm_checks:
        checkbox.setChecked(True)
    window.partial_confirm.setChecked(True)

    assert "部分计划" in window.plan_banner.label.text()
    assert not window.partial_confirm.isHidden()
    window.close()


def test_execute_fatal_failure_shows_recovery_and_returns_setup(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    _confirm(controller)
    window._set_step(3)
    controller.start_execute()

    recorder.jobs[-1].fail("UNEXPECTED", "safe failure")

    assert window.pages.currentIndex() == 0
    assert "旧计划已失效" in window.setup_error.label.text()
    assert controller.plan is None
    assert controller.formal_report_ref is None
    window.close()


def test_modal_snapshot_cannot_confirm_replaced_plan(
    qapp,
    tmp_path,
    monkeypatch,
):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    replacement = replace(plan, created_at="2026-08-23T00:00:01Z")
    _prime_review(controller, plan)
    window.show_plan_result(controller.plan_result)
    for checkbox in window.confirm_checks:
        checkbox.setChecked(True)

    def replace_during_dialog(_dialog) -> QDialog.DialogCode:
        controller.plan = replacement
        controller.plan_result = _plan_result(replacement)
        controller._plan_generation += 1
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", replace_during_dialog)
    window._confirm_execute()

    assert controller.state is GuiState.DRY_RUN_REVIEW
    assert controller.plan is replacement
    assert not controller.current_plan_confirmed
    assert recorder.jobs == []
    assert "替换" in window.plan_banner.label.text()
    window.close()


def test_report_authority_uses_typed_execution_result(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    plan.options.output_dir.mkdir(parents=True, exist_ok=True)
    (plan.options.output_dir / "summary.json").write_text("{}", encoding="utf-8")
    controller.dry_run_report_ref = ReportReference(
        "DRY_RUN", plan.plan_id, plan.options.output_dir,
        plan.options.output_dir / "summary.json", 1,
    )
    controller._operation = WorkerOperation.EXECUTE
    controller._on_completed(_execution(plan, stale=True, reports_written=False))
    window._refresh_report_action()
    assert controller.formal_report_ref is None
    assert window.open_report_button.text() == "查看预演报告"
    window.close()


def test_midrun_zero_row_formal_report_is_authoritative(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_review(controller, plan)
    plan.options.output_dir.mkdir(parents=True, exist_ok=True)
    (plan.options.output_dir / "summary.json").write_text("{}", encoding="utf-8")
    controller._operation = WorkerOperation.EXECUTE
    controller._execution_generation = 3
    controller._on_completed(
        _execution(
            plan,
            items=(),
            processed_count=0,
            remaining_count=1,
            stale=True,
            reports_written=True,
        )
    )
    window._refresh_report_action()
    assert controller.formal_report_ref is not None
    assert window.open_report_button.text() == "打开本次执行报告"
    window.close()


def test_missing_formal_report_never_falls_back_to_dry_run(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = MainWindow(controller=controller, auto_environment_check=False)
    output = tmp_path / "output"
    output.mkdir()
    dry_path = output / "dry-summary.json"
    dry_path.write_text("{}", encoding="utf-8")
    controller.dry_run_report_ref = ReportReference(
        "DRY_RUN", "p", output, dry_path, 1,
    )
    controller.formal_report_ref = ReportReference(
        "EXECUTION", "p", output, output / "missing-summary.json", 2,
    )
    window._refresh_report_action()
    assert window.open_report_button.text() == "本次执行报告已不存在"
    assert not window.open_report_button.isEnabled()
    window.close()

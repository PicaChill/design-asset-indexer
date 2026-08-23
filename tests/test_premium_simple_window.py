from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from design_asset_indexer.gui import app
from design_asset_indexer.gui.controller import GuiState, ReportReference, WorkflowController
from design_asset_indexer.gui.premium_simple_window import (
    ConfirmationDialog,
    PremiumPage,
    PremiumSimpleWindow,
    suggest_sibling_output,
)
from design_asset_indexer.gui.workers import EnvironmentCheckResult, WorkerOperation
from design_asset_indexer.workflow_models import (
    ExecutionItemResult,
    InspectItem,
    PlanItem,
    SignatureExecutionPlan,
    SignatureRule,
)
from tests.test_gui import (
    JobRecorder,
    _execution,
    _inspect,
    _options,
    _plan,
    _plan_result,
    _prime_review,
)


@pytest.fixture(scope="session")
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application
    application.closeAllWindows()
    for widget in application.topLevelWidgets():
        widget.deleteLater()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()
    application.quit()


class AcceptedConfirmation:
    def __init__(self, **kwargs) -> None:
        self.plan = kwargs["plan"]
        self.partial_acknowledged = kwargs["partial"]

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


def _show(window: PremiumSimpleWindow, qapp) -> None:
    window.show()
    qapp.processEvents()


def _prepare_setup(window: PremiumSimpleWindow, tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    window.input_picker.set_path(str(source))
    window.output_picker.set_path(str(output))
    return source, output


def _prime_window_review(
    window: PremiumSimpleWindow,
    controller: WorkflowController,
    plan: SignatureExecutionPlan,
) -> None:
    _prime_review(controller, plan)
    window.show_plan_result(controller.plan_result)


def test_public_app_creates_premium_simple_window(qapp):
    window = app.create_public_window(auto_environment_check=False)
    assert isinstance(window, PremiumSimpleWindow)
    assert all(widget.objectName() != "StepRail" for widget in window.findChildren(QWidget))
    window.close()


def test_public_window_is_novice_first_and_collapsed_by_default(qapp):
    window = PremiumSimpleWindow(auto_environment_check=False)
    _show(window, qapp)
    assert all(widget.objectName() != "StepRail" for widget in window.findChildren(QWidget))
    assert not window.advanced_disclosure.expanded
    assert not window.preview_details.expanded
    assert not window.executing_details.expanded
    assert "日志" not in window.current_visible_text()
    assert len(window.current_primary_buttons()) == 1
    window.close()


@pytest.mark.parametrize(
    ("page", "expected"),
    (
        (PremiumPage.SETUP, "检查 PSD"),
        (PremiumPage.TEXT_SELECTION, "查看修改预览"),
        (PremiumPage.PREVIEW, "确认并开始处理"),
        (PremiumPage.EXECUTING, None),
        (PremiumPage.RESULT, "打开输出文件夹"),
        (PremiumPage.FATAL, "返回重新检查"),
    ),
)
def test_one_primary_action_per_page(qapp, page, expected):
    window = PremiumSimpleWindow(auto_environment_check=False)
    _show(window, qapp)
    window.set_page(page)
    qapp.processEvents()
    primary = window.current_primary_buttons()
    if expected is None:
        assert primary == []
    else:
        assert [button.text() for button in primary] == [expected]
    window.close()


def test_photoshop_pill_uses_typed_environment_result(qapp):
    window = PremiumSimpleWindow(auto_environment_check=False)
    window._on_environment(EnvironmentCheckResult(True, "25.0", "", ""))
    assert "已连接" in window.photoshop_pill.text()
    assert window.photoshop_pill.property("available") == "true"
    window._on_environment(EnvironmentCheckResult(False, None, "NO_APP", "safe"))
    assert "未连接" in window.photoshop_pill.text()
    assert window.photoshop_pill.property("available") == "false"
    window.close()


def test_auto_output_is_sibling_and_does_not_create_directory(qapp, tmp_path):
    window = PremiumSimpleWindow(auto_environment_check=False)
    source = tmp_path / "素材"
    source.mkdir()
    expected = tmp_path / "素材_署名替换输出"
    window.input_picker.set_path(str(source))
    assert Path(window.output_picker.path) == expected
    assert expected.parent == source.parent
    assert source not in expected.parents
    assert not expected.exists()
    assert window.output_mode == "AUTO"
    window.close()


def test_drive_root_has_no_auto_output_suggestion():
    assert suggest_sibling_output("C:\\") is None


def test_manual_output_is_not_silently_overwritten(qapp, tmp_path):
    window = PremiumSimpleWindow(auto_environment_check=False)
    first = tmp_path / "first"
    second = tmp_path / "second"
    manual = tmp_path / "manual-output"
    first.mkdir()
    second.mkdir()
    window.input_picker.set_path(str(first))
    window.output_picker.set_path(str(manual))
    assert window.output_mode == "MANUAL"
    window.input_picker.set_path(str(second))
    assert Path(window.output_picker.path) == manual
    window.close()


def test_restore_auto_output_requires_explicit_action(qapp, tmp_path):
    window = PremiumSimpleWindow(auto_environment_check=False)
    source = tmp_path / "source"
    source.mkdir()
    window.input_picker.set_path(str(source))
    window.output_picker.set_path(str(tmp_path / "manual"))
    window._restore_auto_output()
    assert window.output_mode == "AUTO"
    assert Path(window.output_picker.path) == tmp_path / "source_署名替换输出"
    window.close()


def test_setup_mutation_invalidates_existing_review(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_window_review(window, controller, plan)
    window.input_picker.set_path(str(tmp_path / "different-source"))
    assert controller.state is GuiState.SETUP
    assert controller.plan is None
    assert window.current_page is PremiumPage.SETUP
    assert "重新检查" in window.setup_banner.label.text()
    window.close()


def test_rule_mutation_invalidates_plan_and_returns_to_selection(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    controller.inspect_result = _inspect()
    window._inspect_result = controller.inspect_result
    window._text_items = {"OLD_TEXT": controller.inspect_result.items}
    window._selected_old_text = "OLD_TEXT"
    _prime_window_review(window, controller, plan)
    window.new_text_edit.setText("CHANGED_TEXT")
    assert controller.state is GuiState.INSPECTED
    assert controller.plan is None
    assert window.current_page is PremiumPage.TEXT_SELECTION
    assert "重新查看修改预览" in window.rule_banner.label.text()
    window.close()


def test_inspect_button_calls_controller_and_double_action_starts_one_job(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    source, output = _prepare_setup(window, tmp_path)
    window._start_inspect()
    window._start_inspect()
    assert len(recorder.jobs) == 1
    request = recorder.jobs[0].request
    assert request.operation is WorkerOperation.INSPECT
    assert request.options is not None
    assert request.options.input_dir == source.resolve()
    assert request.options.output_dir == output.resolve()
    recorder.jobs[0].complete(_inspect())
    window.close()


def test_inspect_result_aggregates_text_for_presentation(qapp):
    window = PremiumSimpleWindow(auto_environment_check=False)
    first = _inspect().items[0]
    second = replace(first, relative_path="other.psd", layer_path="Other/Signature")
    result = replace(
        _inspect(),
        items=(first, second),
        candidate_count=2,
        selected_count=2,
        processed_count=2,
    )
    window.show_inspect_result(result)
    assert window._selected_old_text == "OLD_TEXT"
    buttons = window.choice_group.buttons()
    assert len(buttons) == 1
    assert buttons[0].text() == "OLD_TEXT"
    assert "2 个 PSD" in window.selection_title.text()
    window.close()


def test_layer_detail_is_on_demand_and_exact_name_flows_to_rule(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    first = _inspect().items[0]
    second = replace(first, relative_path="other.psd", layer_name="Other", layer_path="Other")
    result = replace(
        _inspect(),
        items=(first, second),
        candidate_count=2,
        selected_count=2,
        processed_count=2,
    )
    controller.options = _options(tmp_path / "source", tmp_path / "output")
    controller.inspect_result = result
    controller._set_state(GuiState.INSPECTED)
    window.show_inspect_result(result)
    assert not window.layer_disclosure.isHidden()
    window.layer_name_combo.setCurrentIndex(1)
    window.new_text_edit.setText("NEW_TEXT")
    window._start_plan()
    assert len(recorder.jobs) == 1
    rule = recorder.jobs[0].request.rule
    assert rule is not None
    assert rule.old_text == "OLD_TEXT"
    assert rule.new_text == "NEW_TEXT"
    assert rule.layer_name in {"Other", "Signature"}
    recorder.jobs[0].complete(_plan_result(_plan(controller.options)))
    window.close()


def test_preview_double_action_starts_one_plan_job(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    options = _options(tmp_path / "source", tmp_path / "output")
    controller.options = options
    controller.inspect_result = _inspect()
    controller._set_state(GuiState.INSPECTED)
    window.show_inspect_result(controller.inspect_result)
    window.new_text_edit.setText("NEW_TEXT")
    window._start_plan()
    window._start_plan()
    assert len(recorder.jobs) == 1
    assert recorder.jobs[0].request.operation is WorkerOperation.PLAN
    plan = _plan(options)
    recorder.jobs[0].complete(_plan_result(plan))
    window.close()


def test_preview_uses_typed_decisions_and_approved_ambiguous_wording(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    base = _plan(_options(tmp_path / "source", tmp_path / "output"))
    items = (
        base.items[0],
        PlanItem("b.psd", "SKIP_NO_MATCH", 0, "b.psd"),
        PlanItem("c.psd", "SKIP_EXISTS", 1, "c.psd"),
        PlanItem("d.psd", "SKIP_AMBIGUOUS", 2, "d.psd"),
        PlanItem("e.psd", "ERROR", 0, "e.psd", "SAFE_ERROR"),
    )
    plan = replace(
        base,
        items=items,
        candidate_relative_paths=tuple(item.relative_path for item in items),
    )
    _prime_window_review(window, controller, plan)
    assert window.preview_metrics["change"].text() == "1"
    assert window.preview_metrics["skip"].text() == "2"
    assert window.preview_metrics["ambiguous"].text() == "1"
    assert "需确认（暂不处理）" in window.current_visible_text()
    assert window.preview_error_line.isVisible() is False or "1 个文件" in window.preview_error_line.text()
    window.close()


def test_confirm_binds_exact_plan_id_generation_and_frozen_execute(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(
        controller=controller,
        auto_environment_check=False,
        confirmation_factory=AcceptedConfirmation,
    )
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_window_review(window, controller, plan)
    generation = controller.plan_generation
    assert window._reviewed_plan is plan
    assert window._reviewed_plan_id == plan.plan_id
    assert window._reviewed_generation == generation
    window._confirm_and_execute()
    assert len(recorder.jobs) == 1
    request = recorder.jobs[0].request
    assert request.operation is WorkerOperation.EXECUTE
    assert request.plan is plan
    assert request.options is None
    assert request.rule is None
    assert controller.state is GuiState.EXECUTING
    recorder.jobs[0].complete(_execution(plan))
    window.close()


def test_confirm_start_double_action_cannot_create_two_jobs(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(
        controller=controller,
        auto_environment_check=False,
        confirmation_factory=AcceptedConfirmation,
    )
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_window_review(window, controller, plan)
    window._confirm_and_execute()
    window._confirm_and_execute()
    assert len(recorder.jobs) == 1
    assert recorder.jobs[0].request.plan is plan
    recorder.jobs[0].complete(_execution(plan))
    window.close()


def test_confirmation_dialog_requires_partial_ack_only_for_partial_plan(qapp, tmp_path):
    complete = _plan(_options(tmp_path / "source", tmp_path / "output"))
    complete_dialog = ConfirmationDialog(
        parent=None,
        plan=complete,
        will_change=1,
        will_skip=0,
        ambiguous=0,
        partial=False,
    )
    assert complete_dialog.partial_check.isHidden()
    assert complete_dialog.start_button.isEnabled()
    partial = _plan(
        _options(tmp_path / "partial-source", tmp_path / "partial-output"),
        partial=True,
    )
    partial_dialog = ConfirmationDialog(
        parent=None,
        plan=partial,
        will_change=1,
        will_skip=0,
        ambiguous=0,
        partial=True,
    )
    assert not partial_dialog.partial_check.isHidden()
    assert not partial_dialog.start_button.isEnabled()
    partial_dialog.partial_check.setChecked(True)
    assert partial_dialog.start_button.isEnabled()
    complete_dialog.close()
    partial_dialog.close()


def test_modal_plan_replacement_is_rejected_without_execute(qapp, tmp_path):
    class ReplacingConfirmation(AcceptedConfirmation):
        def exec(self) -> QDialog.DialogCode:
            controller.plan = replace(self.plan, created_at="later")
            controller.plan_result = _plan_result(controller.plan)
            controller._plan_generation += 1
            return QDialog.DialogCode.Accepted

    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(
        controller=controller,
        auto_environment_check=False,
        confirmation_factory=ReplacingConfirmation,
    )
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_window_review(window, controller, plan)
    window._confirm_and_execute()
    assert recorder.jobs == []
    assert not controller.current_plan_confirmed
    assert "替换" in window.preview_banner.label.text()
    window.close()


def test_busy_state_disables_mutation_controls(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    _prepare_setup(window, tmp_path)
    window._start_inspect()
    assert not window.input_picker.isEnabled()
    assert not window.output_picker.isEnabled()
    assert not window.recursive_check.isEnabled()
    assert not window.max_files_spin.isEnabled()
    assert not window.include_edit.isEnabled()
    recorder.jobs[0].complete(_inspect())
    window.close()


def test_synchronous_state_callback_cannot_launch_second_transaction(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    _prepare_setup(window, tmp_path)
    controller.state_changed.connect(
        lambda state: window._start_inspect() if state is GuiState.INSPECTING else None
    )
    window._start_inspect()
    assert len(recorder.jobs) == 1
    recorder.jobs[0].complete(_inspect())
    window.close()


def test_synchronous_busy_callback_cannot_launch_second_transaction(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    _prepare_setup(window, tmp_path)
    controller.busy_changed.connect(
        lambda busy, _label: window._start_inspect() if busy else None
    )
    window._start_inspect()
    assert len(recorder.jobs) == 1
    recorder.jobs[0].complete(_inspect())
    window.close()


def test_cancel_uses_controller_cooperative_token(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    _prepare_setup(window, tmp_path)
    window._start_inspect()
    window._request_cancel()
    assert recorder.jobs[0].request.cancellation_token.cancelled
    recorder.jobs[0].complete(replace(_inspect(), cancelled=True))
    window.close()


def test_typed_execution_events_drive_progress(qapp):
    from design_asset_indexer.workflow_models import WorkflowEvent, WorkflowEventKind, WorkflowPhase

    window = PremiumSimpleWindow(auto_environment_check=False)
    window._on_event(WorkflowEvent(WorkflowPhase.EXECUTION, WorkflowEventKind.RUN_STARTED, 0, 2))
    window._on_event(
        WorkflowEvent(
            WorkflowPhase.EXECUTION,
            WorkflowEventKind.FILE_STARTED,
            1,
            2,
            "folder/one.psd",
        )
    )
    window._on_event(
        WorkflowEvent(
            WorkflowPhase.EXECUTION,
            WorkflowEventKind.FILE_RESULT,
            1,
            2,
            "folder/one.psd",
            "REPLACED",
        )
    )
    assert window.current_file_label.text() == "one.psd"
    assert window.execute_metrics["success"].text() == "1"
    assert window.execute_progress.value() == 1
    window.close()


def test_result_authority_never_labels_dry_run_as_formal(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    output = tmp_path / "output"
    output.mkdir()
    dry = output / "summary.json"
    dry.write_text("{}", encoding="utf-8")
    controller.dry_run_report_ref = ReportReference("DRY_RUN", "p", output, dry, 1)
    controller.formal_report_ref = None
    window._refresh_formal_report_action()
    assert window.open_formal_report_button.text() == "无可用正式报告"
    assert not window.open_formal_report_button.isEnabled()
    window.close()


def test_formal_report_action_requires_authoritative_existing_ref(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    output = tmp_path / "output"
    output.mkdir()
    summary = output / "summary.json"
    summary.write_text("{}", encoding="utf-8")
    controller.formal_report_ref = ReportReference("EXECUTION", "p", output, summary, 1)
    window._refresh_formal_report_action()
    assert window.open_formal_report_button.text() == "打开本次执行报告"
    assert window.open_formal_report_button.isEnabled()
    window.close()


@pytest.mark.parametrize(
    ("changes", "title_fragment"),
    (
        ({"cancelled": True, "remaining_count": 1}, "任务已停止"),
        ({"stale": True, "remaining_count": 1}, "需要重新检查"),
    ),
)
def test_cancelled_and_stale_results_are_not_called_complete(
    qapp, tmp_path, changes, title_fragment
):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    controller.plan = plan
    result = _execution(plan, **changes)
    window.show_execution_result(result)
    assert title_fragment in window.result_title.text()
    assert window.result_title.text() != "处理完成"
    window.close()


def test_failure_result_auto_expands_safe_summary(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    controller.plan = plan
    failed = ExecutionItemResult(
        "folder/sample.psd",
        "FAILED_SAVE",
        1,
        0,
        "folder/sample.psd",
        "PHOTOSHOP_SAVE_FAILED",
        "not displayed",
    )
    result = _execution(plan, items=(failed,))
    window.show_execution_result(result)
    assert window.result_details.expanded
    assert "需要查看" in window.result_title.text()
    assert window.result_table.item(0, 2).text() == "PHOTOSHOP_SAVE_FAILED"
    window.close()


def test_execute_fatal_failure_shows_recheck_and_old_plan_retry_is_unavailable(qapp, tmp_path):
    recorder = JobRecorder()
    controller = WorkflowController(job_factory=recorder)
    window = PremiumSimpleWindow(
        controller=controller,
        auto_environment_check=False,
        confirmation_factory=AcceptedConfirmation,
    )
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_window_review(window, controller, plan)
    window._confirm_and_execute()
    recorder.jobs[-1].fail("UNEXPECTED", "safe failure")
    assert window.current_page is PremiumPage.FATAL
    assert controller.state is GuiState.SETUP
    assert controller.plan is None
    assert "重新检查" in window.current_visible_text()
    assert all(button.text() != "确认并开始处理" for button in window.current_primary_buttons())
    window.close()


def test_default_production_pages_hide_technical_terms(qapp, tmp_path):
    controller = WorkflowController(job_factory=JobRecorder())
    window = PremiumSimpleWindow(controller=controller, auto_environment_check=False)
    _show(window, qapp)
    texts = []
    texts.append(window.current_visible_text())
    window.show_inspect_result(_inspect())
    texts.append(window.current_visible_text())
    plan = _plan(_options(tmp_path / "source", tmp_path / "output"))
    _prime_window_review(window, controller, plan)
    texts.append(window.current_visible_text())
    visible = "\n".join(texts).casefold()
    for forbidden in ("dry-run", "plan_id", "partial_plan", "stale", "fail-closed"):
        assert forbidden not in visible
    window.close()

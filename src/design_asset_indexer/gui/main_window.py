"""Five-step Windows GUI for the safe PSD signature workflow."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..workflow import build_public_diagnostic
from ..workflow_models import (
    ExecutionRunResult,
    InspectRunResult,
    PlanRunResult,
    SignatureRule,
    WorkflowEvent,
)
from .controller import GuiState, WorkflowController
from .models import (
    InspectFilterProxyModel,
    InspectTableModel,
    PlanTableModel,
    ResultFilterProxyModel,
    ResultTableModel,
    status_counts,
)
from .widgets import Banner, PathPicker, StatusCard
from .workers import EnvironmentCheckResult


STEP_LABELS = (
    "1  设置",
    "2  检查文字图层",
    "3  预演确认",
    "4  正式执行",
    "5  结果",
)


def _title(text: str, subtitle: str) -> tuple[QLabel, QLabel]:
    heading = QLabel(text)
    heading.setObjectName("PageTitle")
    hint = QLabel(subtitle)
    hint.setObjectName("Muted")
    hint.setWordWrap(True)
    return heading, hint


def _table() -> QTableView:
    view = QTableView()
    view.setAlternatingRowColors(True)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.verticalHeader().setVisible(False)
    view.horizontalHeader().setStretchLastSection(True)
    return view


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        controller: WorkflowController | None = None,
        auto_environment_check: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("表情包 PSD 批量署名替换")
        self.resize(1180, 780)
        self.setMinimumSize(1000, 680)
        self.controller = controller or WorkflowController(parent=self)
        self._allow_close = False
        self._close_when_finished = False

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(12)
        outer.addWidget(self._build_top_bar())

        content = QHBoxLayout()
        content.setSpacing(12)
        content.addWidget(self._build_step_rail())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_setup_page())
        self.pages.addWidget(self._build_inspect_page())
        self.pages.addWidget(self._build_plan_page())
        self.pages.addWidget(self._build_execute_page())
        self.pages.addWidget(self._build_result_page())
        content.addWidget(self.pages, 1)
        outer.addLayout(content, 1)
        outer.addWidget(self._build_job_bar())

        self._connect_controller()
        self._set_step(0)
        self._on_busy(False, "")
        if auto_environment_check:
            QTimer.singleShot(0, self._safe_environment_check)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 12)
        title = QLabel("🖊️ 表情包 PSD 批量署名替换")
        title.setObjectName("Title")
        self.photoshop_pill = QLabel("Photoshop：正在检查")
        self.photoshop_pill.setObjectName("WarningText")
        self.help_button = QPushButton("使用说明")
        self.help_button.clicked.connect(self._open_help)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(self.photoshop_pill)
        layout.addWidget(self.help_button)
        return bar

    def _build_step_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("StepRail")
        rail.setFixedWidth(190)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(10, 12, 10, 12)
        self.step_buttons: list[QPushButton] = []
        for label in STEP_LABELS:
            button = QPushButton(label)
            button.setObjectName("StepButton")
            button.setEnabled(False)
            self.step_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        note = QLabel("输入目录只读\n输出始终隔离")
        note.setObjectName("Muted")
        layout.addWidget(note)
        return rail

    def _scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.viewport().setObjectName("ScrollViewport")
        body = QWidget()
        body.setObjectName("ScrollBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        area.setWidget(body)
        return area, layout

    def _build_setup_page(self) -> QWidget:
        page, layout = self._scroll_page()
        heading, hint = _title(
            "开始一个安全任务",
            "选择原 PSD 所在目录和完全独立的输出目录。正式执行不会覆盖原文件。",
        )
        layout.addWidget(heading)
        layout.addWidget(hint)
        self.setup_banner = Banner(
            "✅ 原 PSD 不会被覆盖 · ⚠️ 写入需要 Windows + Adobe Photoshop · "
            "❌ 不支持栅格化文字 / Smart Object / GIF 成品图",
            "warning",
        )
        layout.addWidget(self.setup_banner)

        form_group = QGroupBox("目录与范围")
        form = QFormLayout(form_group)
        self.input_picker = PathPicker("例如 D:\\素材", "选择 PSD 输入目录")
        self.output_picker = PathPicker("例如 D:\\署名替换输出", "选择独立输出目录")
        self.recursive_check = QCheckBox("递归检查子目录")
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1, 100000)
        self.max_files_spin.setValue(100)
        self.max_files_spin.setSuffix(" 个 PSD")
        form.addRow("输入目录", self.input_picker)
        form.addRow("输出目录", self.output_picker)
        form.addRow("扫描方式", self.recursive_check)
        form.addRow("安全上限", self.max_files_spin)
        layout.addWidget(form_group)

        advanced = QGroupBox("高级设置")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_form = QFormLayout(advanced)
        self.include_edit = QLineEdit("*.psd")
        self.include_edit.setToolTip("通常保持 *.psd；只接受 glob，不改变匹配语义。")
        advanced_label = QLabel("文件匹配")
        advanced_form.addRow(advanced_label, self.include_edit)
        advanced.toggled.connect(lambda expanded: self.include_edit.setVisible(expanded))
        advanced.toggled.connect(lambda expanded: advanced_label.setVisible(expanded))
        self.include_edit.setVisible(False)
        advanced_label.setVisible(False)
        layout.addWidget(advanced)

        self.setup_error = Banner()
        layout.addWidget(self.setup_error)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.inspect_button = QPushButton("检查 Photoshop 和文字图层")
        self.inspect_button.setObjectName("PrimaryButton")
        self.inspect_button.clicked.connect(self._start_inspect)
        actions.addWidget(self.inspect_button)
        layout.addLayout(actions)
        layout.addStretch(1)

        self.input_picker.path_changed.connect(self._setup_changed)
        self.output_picker.path_changed.connect(self._setup_changed)
        self.recursive_check.toggled.connect(self._setup_changed)
        self.max_files_spin.valueChanged.connect(self._setup_changed)
        self.include_edit.textChanged.connect(self._setup_changed)
        return page

    def _build_inspect_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        heading, hint = _title(
            "检查可编辑文字图层",
            "选择一个明确的当前文字作为替换目标。多个完全相同候选会在预演中安全跳过。",
        )
        layout.addWidget(heading)
        layout.addWidget(hint)
        self.inspect_summary = Banner()
        layout.addWidget(self.inspect_summary)
        filters = QHBoxLayout()
        self.inspect_search = QLineEdit()
        self.inspect_search.setPlaceholderText("搜索文字、图层名或图层路径")
        self.inspect_filter = QComboBox()
        self.inspect_filter.addItems(("全部", "有文字", "错误"))
        filters.addWidget(self.inspect_search, 1)
        filters.addWidget(self.inspect_filter)
        layout.addLayout(filters)
        self.inspect_model = InspectTableModel()
        self.inspect_proxy = InspectFilterProxyModel()
        self.inspect_proxy.setSourceModel(self.inspect_model)
        self.inspect_table = _table()
        self.inspect_table.setModel(self.inspect_proxy)
        self.inspect_table.clicked.connect(self._select_inspect_row)
        layout.addWidget(self.inspect_table, 1)
        self.inspect_search.textChanged.connect(self.inspect_proxy.set_search_text)
        self.inspect_filter.currentTextChanged.connect(self.inspect_proxy.set_mode)

        rule_group = QGroupBox("替换条件")
        rule = QGridLayout(rule_group)
        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("从表格选择，或输入需要完全匹配的当前文字")
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("输入新署名文字")
        self.exact_layer_radio = QRadioButton("同时限定所选图层名（更安全）")
        self.any_layer_radio = QRadioButton("只按文字完全匹配")
        self.any_layer_radio.setChecked(True)
        self.selected_layer_name = ""
        rule.addWidget(QLabel("当前文字"), 0, 0)
        rule.addWidget(self.from_edit, 0, 1, 1, 2)
        rule.addWidget(QLabel("新文字"), 1, 0)
        rule.addWidget(self.to_edit, 1, 1, 1, 2)
        rule.addWidget(self.exact_layer_radio, 2, 1)
        rule.addWidget(self.any_layer_radio, 2, 2)
        layout.addWidget(rule_group)
        self.role_warning = Banner()
        layout.addWidget(self.role_warning)
        self.font_warning = Banner(
            "字体与字形：未自动核验。⚠️ 特殊字体或目标字符可能因字体未安装、"
            "缺少字形或 Photoshop 重新排版而变化；建议先用少量 PSD 人工检查。",
            "warning",
        )
        layout.addWidget(self.font_warning)
        self.inspect_rule_error = Banner()
        layout.addWidget(self.inspect_rule_error)
        buttons = QHBoxLayout()
        back = QPushButton("返回设置")
        back.clicked.connect(lambda: self._set_step(0))
        self.plan_button = QPushButton("生成 dry-run 预演")
        self.plan_button.setObjectName("PrimaryButton")
        self.plan_button.clicked.connect(self._start_plan)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(self.plan_button)
        layout.addLayout(buttons)
        self.from_edit.textChanged.connect(self._rule_changed)
        self.to_edit.textChanged.connect(self._rule_changed)
        self.exact_layer_radio.toggled.connect(self._rule_changed)
        return page

    def _build_plan_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        heading, hint = _title(
            "确认 dry-run 预演",
            "这里展示将会发生什么；尚未保存任何修改后的 PSD。",
        )
        layout.addWidget(heading)
        layout.addWidget(hint)
        self.plan_banner = Banner()
        layout.addWidget(self.plan_banner)
        cards = QHBoxLayout()
        self.plan_cards = {
            "WOULD_REPLACE": StatusCard("会修改", "SUCCESS"),
            "SKIP_NO_MATCH": StatusCard("没找到", "WARNING"),
            "SKIP_AMBIGUOUS": StatusCard("多个候选", "WARNING"),
            "SKIP_EXISTS": StatusCard("输出已存在", "WARNING"),
            "ERROR": StatusCard("错误", "ERROR"),
        }
        for card in self.plan_cards.values():
            cards.addWidget(card)
        layout.addLayout(cards)
        self.plan_id_label = QLabel("计划编号：—")
        self.plan_id_label.setObjectName("Muted")
        layout.addWidget(self.plan_id_label)
        self.plan_model = PlanTableModel()
        self.plan_table = _table()
        self.plan_table.setModel(self.plan_model)
        layout.addWidget(self.plan_table, 1)
        confirm_group = QGroupBox("执行前确认")
        confirm_layout = QVBoxLayout(confirm_group)
        self.confirm_checks = (
            QCheckBox("我已核对旧署名和新署名"),
            QCheckBox("如有多个角色，我已在 Photoshop 中人工确认图层对应关系"),
            QCheckBox("我理解特殊字体 / 目标字符视觉效果需要人工验收"),
            QCheckBox("我理解未匹配 PSD 不会复制到输出目录"),
        )
        for checkbox in self.confirm_checks:
            confirm_layout.addWidget(checkbox)
            checkbox.toggled.connect(self._update_execute_enabled)
        self.partial_confirm = QCheckBox(
            "我理解本计划只覆盖安全上限内的文件，未处理项不算完成"
        )
        self.partial_confirm.toggled.connect(self._update_execute_enabled)
        confirm_layout.addWidget(self.partial_confirm)
        layout.addWidget(confirm_group)
        buttons = QHBoxLayout()
        back = QPushButton("返回调整条件")
        back.clicked.connect(lambda: self._set_step(1))
        self.execute_button = QPushButton("正式执行已确认计划")
        self.execute_button.setObjectName("PrimaryButton")
        self.execute_button.setAutoDefault(False)
        self.execute_button.setDefault(False)
        self.execute_button.clicked.connect(self._confirm_execute)
        buttons.addWidget(back)
        buttons.addStretch(1)
        buttons.addWidget(self.execute_button)
        layout.addLayout(buttons)
        return page

    def _build_execute_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        heading, hint = _title(
            "正在正式执行",
            "Photoshop 正按冻结计划逐个处理输出副本。取消会在安全文件边界生效。",
        )
        layout.addWidget(heading)
        layout.addWidget(hint)
        self.execute_banner = Banner(
            "⚠️ 请保持 Photoshop 可用。不要手动移动输入或输出文件。",
            "warning",
        )
        layout.addWidget(self.execute_banner)
        self.execute_progress = QProgressBar()
        self.execute_progress.setRange(0, 1)
        self.execute_progress.setValue(0)
        layout.addWidget(self.execute_progress)
        self.execute_status = QLabel("准备执行…")
        self.execute_status.setObjectName("Muted")
        layout.addWidget(self.execute_status)
        self.execute_cancel = QPushButton("在安全边界取消")
        self.execute_cancel.setObjectName("DangerButton")
        self.execute_cancel.clicked.connect(self._request_cancel)
        layout.addWidget(self.execute_cancel, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        self.result_title = QLabel("处理结果")
        self.result_title.setObjectName("PageTitle")
        layout.addWidget(self.result_title)
        self.result_banner = Banner()
        layout.addWidget(self.result_banner)
        cards = QHBoxLayout()
        self.result_cards = {
            "REPLACED": StatusCard("已替换", "SUCCESS"),
            "SKIPPED_NO_MATCH": StatusCard("未匹配", "WARNING"),
            "SKIPPED_AMBIGUOUS": StatusCard("多候选", "WARNING"),
            "SKIPPED_EXISTS": StatusCard("已存在", "WARNING"),
            "FAILED": StatusCard("失败", "ERROR"),
        }
        for card in self.result_cards.values():
            cards.addWidget(card)
        layout.addLayout(cards)
        filter_row = QHBoxLayout()
        filter_row.addStretch(1)
        self.result_filter = QComboBox()
        self.result_filter.addItems(("全部", "成功", "跳过", "失败"))
        filter_row.addWidget(self.result_filter)
        layout.addLayout(filter_row)
        self.result_model = ResultTableModel()
        self.result_proxy = ResultFilterProxyModel()
        self.result_proxy.setSourceModel(self.result_model)
        self.result_filter.currentTextChanged.connect(self.result_proxy.set_mode)
        self.result_table = _table()
        self.result_table.setModel(self.result_proxy)
        layout.addWidget(self.result_table, 1)
        buttons = QHBoxLayout()
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.clicked.connect(self._open_output)
        self.open_report_button = QPushButton("打开 summary.json")
        self.open_report_button.clicked.connect(self._open_summary)
        self.copy_diagnostic_button = QPushButton("复制安全诊断")
        self.copy_diagnostic_button.clicked.connect(self._copy_diagnostic)
        new_task = QPushButton("新任务")
        new_task.setObjectName("PrimaryButton")
        new_task.clicked.connect(self._new_task)
        for button in (
            self.open_output_button,
            self.open_report_button,
            self.copy_diagnostic_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(new_task)
        layout.addLayout(buttons)
        return page

    def _build_job_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("JobBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        self.job_label = QLabel("就绪")
        self.job_label.setObjectName("Muted")
        self.job_progress = QProgressBar()
        self.job_progress.setMaximumWidth(260)
        self.job_progress.setRange(0, 1)
        self.job_progress.setValue(0)
        self.job_cancel = QPushButton("取消")
        self.job_cancel.setObjectName("DangerButton")
        self.job_cancel.clicked.connect(self._request_cancel)
        layout.addWidget(self.job_label)
        layout.addStretch(1)
        layout.addWidget(self.job_progress)
        layout.addWidget(self.job_cancel)
        return bar

    def _connect_controller(self) -> None:
        self.controller.busy_changed.connect(self._on_busy)
        self.controller.environment_ready.connect(self._on_environment)
        self.controller.inspect_ready.connect(self.show_inspect_result)
        self.controller.plan_ready.connect(self.show_plan_result)
        self.controller.execution_ready.connect(self.show_execution_result)
        self.controller.event_received.connect(self._on_event)
        self.controller.failed.connect(self._on_failure)
        self.controller.job_finished.connect(self._on_job_finished)

    def _safe_environment_check(self) -> None:
        try:
            self.controller.check_environment()
        except RuntimeError:
            return

    def _set_step(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for position, button in enumerate(self.step_buttons):
            button.setProperty("active", position == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _setup_changed(self, *_args) -> None:
        if not self.controller.busy:
            self.controller.invalidate_setup()
            if not self.input_picker.path and not self.output_picker.path:
                self.setup_error.set_message("")
                return
            try:
                self.controller.make_options(
                    self.input_picker.path,
                    self.output_picker.path,
                    recursive=self.recursive_check.isChecked(),
                    include=self.include_edit.text(),
                    max_files=self.max_files_spin.value(),
                )
            except ValueError as error:
                self.setup_error.set_message(str(error), "error")
            else:
                self.setup_error.set_message("")

    def _rule_changed(self, *_args) -> None:
        if not self.controller.busy:
            self.controller.invalidate_rule()
            self.inspect_rule_error.set_message("")

    def _start_inspect(self) -> None:
        try:
            options = self.controller.make_options(
                self.input_picker.path,
                self.output_picker.path,
                recursive=self.recursive_check.isChecked(),
                include=self.include_edit.text(),
                max_files=self.max_files_spin.value(),
            )
            self.controller.start_inspect(options)
        except (ValueError, RuntimeError) as error:
            self.setup_error.set_message(str(error), "error")

    def _select_inspect_row(self, proxy_index) -> None:
        source_index = self.inspect_proxy.mapToSource(proxy_index)
        row = source_index.row()
        item = self.inspect_model.item_at(row)
        self.inspect_model.set_selected_row(row)
        self.selected_layer_name = item.layer_name
        self.from_edit.setText(item.current_text)
        self.exact_layer_radio.setEnabled(bool(item.layer_name))
        if not item.layer_name:
            self.any_layer_radio.setChecked(True)
        same_text_names = {
            candidate.layer_name
            for candidate in self.inspect_model.items
            if candidate.current_text == item.current_text and candidate.layer_name
        }
        if len(same_text_names) > 1:
            self.role_warning.set_message(
                "⚠️ 同一文字出现在多个图层。若对应不同角色，请先在 Photoshop "
                "中人工确认，不要根据‘拷贝 / 副本’等名称推断人物。",
                "warning",
            )
        else:
            self.role_warning.set_message("")

    def _start_plan(self) -> None:
        try:
            layer_name = (
                self.selected_layer_name
                if self.exact_layer_radio.isChecked() and self.selected_layer_name
                else None
            )
            rule = SignatureRule(
                old_text=self.from_edit.text(),
                new_text=self.to_edit.text(),
                layer_name=layer_name,
            )
            self.controller.start_plan(rule)
        except (ValueError, RuntimeError) as error:
            self.inspect_rule_error.set_message(str(error), "error")

    def show_inspect_result(self, result: InspectRunResult) -> None:
        self.inspect_model.set_items(result.items)
        if result.cancelled:
            message, kind = "检查已取消；未检查项不能视为完成。", "warning"
        elif result.max_files_reached or result.unplanned_count:
            message, kind = (
                f"⚠️ 只检查了安全上限内的 {result.selected_count} 个；"
                f"另有 {result.unplanned_count} 个未纳入。",
                "warning",
            )
        else:
            message, kind = (
                f"✅ 已检查 {result.processed_count} 个 PSD，发现 {len(result.items)} 条图层记录。",
                "success",
            )
        self.inspect_summary.set_message(message, kind)
        self._set_step(1)

    def show_plan_result(self, result: PlanRunResult) -> None:
        self.plan_model.set_items(result.items)
        counts = status_counts(result.items, "decision")
        for key, card in self.plan_cards.items():
            card.set_value(counts.get(key, 0))
        if result.plan is not None:
            self.plan_id_label.setText(f"预演编号：{result.plan.plan_id[:8].upper()}")
        else:
            self.plan_id_label.setText("计划编号：未生成")
        partial = result.partial_plan
        self.partial_confirm.setVisible(partial)
        self.partial_confirm.setChecked(False)
        for checkbox in self.confirm_checks:
            checkbox.setChecked(False)
        if result.cancelled:
            message, kind = "预演已取消，不能正式执行。", "warning"
        elif result.stale or result.plan is None:
            message, kind = "输入或输出在预演期间发生变化，请返回重新检查。", "error"
        elif partial:
            message, kind = (
                f"⚠️ 部分计划：纳入 {result.selected_count} 个，"
                f"仍有 {result.unplanned_count} 个不在本次范围内。",
                "warning",
            )
        else:
            message, kind = "✅ dry-run 完成。请逐项确认后再正式执行。", "success"
        self.plan_banner.set_message(message, kind)
        self._update_execute_enabled()
        self._set_step(2)

    def _update_execute_enabled(self) -> None:
        confirmations = all(box.isChecked() for box in self.confirm_checks)
        result = self.controller.plan_result
        if result is not None and result.partial_plan:
            confirmations = confirmations and self.partial_confirm.isChecked()
        self.execute_button.setEnabled(
            confirmations
            and self.controller.plan is not None
            and not self.controller.busy
        )

    def _confirm_execute(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("最后确认")
        layout = QVBoxLayout(dialog)
        plan = self.controller.plan
        would_replace = (
            sum(item.decision == "WOULD_REPLACE" for item in plan.items)
            if plan is not None
            else 0
        )
        output = str(plan.options.output_dir) if plan is not None else "—"
        message = QLabel(
            f"即将处理 {would_replace} 个 WOULD_REPLACE 文件。\n"
            "原 PSD 不覆盖。\n"
            f"输出目录：{output}"
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确认执行")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setAutoDefault(False)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setDefault(False)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._set_step(3)
            self.controller.start_execute()
        except RuntimeError as error:
            self.plan_banner.set_message(str(error), "error")
            self._set_step(2)

    def show_execution_result(self, result: ExecutionRunResult) -> None:
        self.result_model.set_items(result.items)
        raw = status_counts(result.items, "status")
        replaced = raw.get("REPLACED", 0)
        failed = sum(value for key, value in raw.items() if key.startswith("FAILED"))
        self.result_cards["REPLACED"].set_value(replaced)
        self.result_cards["SKIPPED_NO_MATCH"].set_value(raw.get("SKIPPED_NO_MATCH", 0))
        self.result_cards["SKIPPED_AMBIGUOUS"].set_value(
            raw.get("SKIPPED_AMBIGUOUS", 0)
        )
        self.result_cards["SKIPPED_EXISTS"].set_value(raw.get("SKIPPED_EXISTS", 0))
        self.result_cards["FAILED"].set_value(failed)
        if result.stale:
            title = "计划已过期，执行已安全停止"
            message, kind = "输入或输出发生变化。未处理项没有继续执行。", "error"
        elif result.cancelled:
            title = "任务已在安全边界取消"
            message, kind = "已完成项保留；其余项目未处理。", "warning"
        elif result.partial_plan:
            title = "本次计划已完成（仍有未纳入项）"
            message, kind = "⚠️ 只完成已确认计划；未纳入项不算处理完成。", "warning"
        elif failed:
            title = "任务完成，但有失败项"
            message, kind = "请查看失败类别；失败输出会按 fail-clean 规则清理。", "error"
        else:
            title = "任务完成"
            message, kind = "✅ 已按确认计划完成，原 PSD 保持不变。", "success"
        self.result_title.setText(title)
        self.result_banner.set_message(message, kind)
        self._set_step(4)

    def _on_environment(self, result: EnvironmentCheckResult) -> None:
        if result.available:
            suffix = f" {result.version}" if result.version else ""
            self.photoshop_pill.setText(f"Photoshop：可用{suffix}")
            self.photoshop_pill.setObjectName("SuccessText")
        else:
            self.photoshop_pill.setText("Photoshop：不可用")
            self.photoshop_pill.setObjectName("ErrorText")
        self.photoshop_pill.style().unpolish(self.photoshop_pill)
        self.photoshop_pill.style().polish(self.photoshop_pill)

    def _on_busy(self, busy: bool, label: str) -> None:
        self.job_label.setText(label if busy else "就绪")
        self.job_cancel.setVisible(busy)
        self.job_progress.setRange(0, 0 if busy else 1)
        self.job_progress.setValue(0 if busy else 1)
        self.inspect_button.setEnabled(not busy)
        self.plan_button.setEnabled(not busy)
        self.execute_cancel.setEnabled(busy)
        for widget in (
            self.input_picker,
            self.output_picker,
            self.recursive_check,
            self.max_files_spin,
            self.include_edit,
            self.from_edit,
            self.to_edit,
            self.exact_layer_radio,
            self.any_layer_radio,
        ):
            widget.setEnabled(not busy)
        self._update_execute_enabled()

    def _on_event(self, event: WorkflowEvent) -> None:
        total = max(1, event.total)
        value = min(event.index, total)
        self.job_progress.setRange(0, total)
        self.job_progress.setValue(value)
        if self.pages.currentIndex() == 3:
            self.execute_progress.setRange(0, total)
            self.execute_progress.setValue(value)
            self.execute_status.setText(
                f"{event.index}/{event.total}"
                + (f" · {event.relative_path}" if event.relative_path else "")
            )

    def _request_cancel(self) -> None:
        self.controller.cancel()
        self.job_label.setText("正在安全停止…当前 PSD 结束后不再处理下一个文件。")
        self.execute_status.setText("正在安全停止…")
        self.job_cancel.setEnabled(False)
        self.execute_cancel.setEnabled(False)

    def _on_job_finished(self) -> None:
        self.job_cancel.setEnabled(True)
        if self._close_when_finished:
            self._allow_close = True
            self.close()

    def _on_failure(self, code: str, message: str) -> None:
        safe = f"{code}: {message}"
        if self.pages.currentIndex() == 0:
            self.setup_error.set_message(safe, "error")
        elif self.pages.currentIndex() == 1:
            self.inspect_rule_error.set_message(safe, "error")
        elif self.pages.currentIndex() == 3:
            self.execute_banner.set_message(safe, "error")
        else:
            self.plan_banner.set_message(safe, "error")

    def _open_help(self) -> None:
        path = Path(__file__).resolve().parents[3] / "docs" / "WINDOWS_PSD_SIGNATURE_GUIDE_CN.md"
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self,
                "使用说明",
                "请查看项目 README 和 docs/WINDOWS_PSD_SIGNATURE_GUIDE_CN.md。",
            )

    def _open_output(self) -> None:
        options = self.controller.options
        if options is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(options.output_dir)))

    def _open_summary(self) -> None:
        options = self.controller.options
        if options is not None:
            report = options.output_dir / "summary.json"
            if report.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    def _copy_diagnostic(self) -> None:
        result = self.controller.execution_result
        if result is None:
            return
        diagnostic = build_public_diagnostic(result)
        QApplication.clipboard().setText(
            json.dumps(diagnostic, ensure_ascii=False, indent=2, sort_keys=True)
        )
        self.result_banner.set_message("✅ 已复制不含路径、文件名和文字的安全诊断。", "success")

    def _new_task(self) -> None:
        self.controller.invalidate_setup()
        self.inspect_model.set_items(())
        self.plan_model.set_items(())
        self.result_model.set_items(())
        self.from_edit.clear()
        self.to_edit.clear()
        self._set_step(0)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._allow_close or not self.controller.busy:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "任务仍在运行",
            "现在关闭不会强制终止 Photoshop。是否请求在安全文件边界取消？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._close_when_finished = True
            self._request_cancel()
        event.ignore()

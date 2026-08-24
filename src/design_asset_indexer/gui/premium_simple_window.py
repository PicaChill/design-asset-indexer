"""Novice-first Premium Simple presentation for the safe PSD workflow.

The window is deliberately presentation-only. WorkflowController remains the
single authority for setup validation, inspect, planning, confirmation,
execution, cancellation, reports, and fail-closed recovery.
"""

from __future__ import annotations

import json
from collections import defaultdict
from enum import Enum
from pathlib import Path, PurePosixPath
import sys
from typing import Callable

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..workflow import build_public_diagnostic
from ..workflow_models import (
    ExecutionRunResult,
    InspectItem,
    InspectRunResult,
    PlanItem,
    PlanRunResult,
    SignatureExecutionPlan,
    SignatureRule,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowPhase,
)
from .controller import GuiState, WorkflowController
from .theme import TOKENS, build_application_font
from .widgets import PathPicker
from .workers import EnvironmentCheckResult


class PremiumPage(str, Enum):
    """Presentation pages; business state remains owned by GuiState."""

    SETUP = "setup"
    TEXT_SELECTION = "text-selection"
    PREVIEW = "preview"
    EXECUTING = "executing"
    RESULT = "result"
    FATAL = "fatal"


def suggest_sibling_output(input_text: str) -> str | None:
    """Suggest a sibling output path without touching the filesystem."""

    value = input_text.strip()
    if not value:
        return None
    source = Path(value).expanduser()
    if source.anchor and source == Path(source.anchor):
        return None
    if not source.name:
        return None
    return str(source.parent / f"{source.name}_署名替换输出")


def resolve_help_document() -> Path | None:
    """Find the source or portable help document without assuming a checkout."""

    candidates = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "WINDOWS_PSD_SIGNATURE_GUIDE_CN.md",
        Path(sys.executable).resolve().parent / "README.txt",
    )
    return next((path for path in candidates if path.is_file()), None)


def premium_stylesheet() -> str:
    """Return the approved calm, low-border Premium Simple visual language."""

    t = TOKENS
    return f"""
    * {{ font-size: 14px; color: {t['TEXT']}; }}
    QMainWindow, QWidget#PremiumRoot, QWidget#MainViewport,
    QWidget#MainBody, QWidget#PremiumPage {{ background: {t['BG']}; }}
    QDialog#ConfirmationDialog {{ background: {t['BG']}; }}
    QFrame#TopBar {{
        background: rgba(24, 28, 36, 0.82);
        border: none;
        border-bottom: 1px solid #252c38;
    }}
    QLabel#Brand {{ font-size: 19px; font-weight: 700; letter-spacing: 0.4px; }}
    QLabel#Version {{ color: {t['TEXT_MUTED']}; font-size: 12px; }}
    QLabel#ConnectionPill {{
        color: #f1d58a;
        background: rgba(255, 209, 102, 0.08);
        border: 1px solid rgba(255, 209, 102, 0.28);
        border-radius: 14px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#ConnectionPill[available="true"] {{
        color: #bdeed1;
        background: rgba(69, 212, 131, 0.10);
        border-color: rgba(69, 212, 131, 0.30);
    }}
    QLabel#ConnectionPill[available="false"] {{
        color: #ffc2c2;
        background: rgba(255, 107, 107, 0.08);
        border-color: rgba(255, 107, 107, 0.28);
    }}
    QLabel#Eyebrow {{
        color: {t['PRIMARY']};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#PageTitle {{ font-size: 29px; font-weight: 700; }}
    QLabel#Subtitle {{ color: {t['TEXT_MUTED']}; font-size: 15px; }}
    QLabel#FieldLabel {{ color: #cbd2de; font-size: 13px; font-weight: 600; }}
    QLabel#Muted, QLabel#FooterText {{ color: {t['TEXT_MUTED']}; }}
    QLabel#SafetyText {{
        color: #bec8d8;
        background: rgba(122, 162, 255, 0.07);
        border-radius: 9px;
        padding: 12px 14px;
    }}
    QLabel#SuccessIcon {{ color: {t['SUCCESS']}; font-size: 42px; font-weight: 700; }}
    QLabel#FailureIcon {{ color: {t['ERROR']}; font-size: 19px; font-weight: 700; }}
    QLabel#LargeNumber {{ font-size: 36px; font-weight: 700; }}
    QLabel#MetricNumber {{ font-size: 28px; font-weight: 700; }}
    QLabel#MetricLabel {{ color: {t['TEXT_MUTED']}; font-size: 13px; }}
    QLabel#WarningLine {{
        color: #f1d58a;
        background: rgba(255, 209, 102, 0.07);
        border-radius: 8px;
        padding: 10px 12px;
    }}
    QLabel#ErrorLine {{
        color: #ffc2c2;
        background: rgba(255, 107, 107, 0.08);
        border-radius: 8px;
        padding: 10px 12px;
    }}
    QFrame#Surface, QFrame#ConfirmationSurface {{
        background: #171c25;
        border: 1px solid #252d3a;
        border-radius: 16px;
    }}
    QFrame#ConfirmationSurface {{ background: #1a202b; border-color: #354258; }}
    QFrame#SummaryStrip {{
        background: #171c25;
        border: 1px solid #252d3a;
        border-radius: 14px;
    }}
    QFrame#ChoiceRow {{
        background: #1b212c;
        border: 1px solid #293240;
        border-radius: 10px;
    }}
    QFrame#ChoiceRow[selected="true"] {{
        background: rgba(122, 162, 255, 0.09);
        border-color: {t['PRIMARY']};
    }}
    QFrame#FailureDetail {{
        background: rgba(255, 107, 107, 0.06);
        border: 1px solid rgba(255, 107, 107, 0.28);
        border-radius: 12px;
    }}
    QLineEdit, QSpinBox, QComboBox {{
        min-height: 42px;
        padding: 0 12px;
        background: #1d2430;
        border: 1px solid #303a49;
        border-radius: 9px;
        selection-background-color: {t['PRIMARY']};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {t['PRIMARY']}; }}
    QPushButton, QToolButton {{
        min-height: 40px;
        padding: 0 16px;
        background: transparent;
        border: 1px solid #303a49;
        border-radius: 9px;
        font-weight: 600;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: rgba(122, 162, 255, 0.07);
        border-color: #4d6183;
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: #657080;
        background: #171b23;
        border-color: #282f3b;
    }}
    QPushButton#PrimaryButton {{
        min-height: 48px;
        color: #0b1020;
        background: {t['PRIMARY']};
        border-color: {t['PRIMARY']};
        font-size: 15px;
        font-weight: 700;
    }}
    QPushButton#PrimaryButton:hover {{ background: {t['PRIMARY_HOVER']}; }}
    QPushButton#PrimaryButton:disabled {{
        color: {t['TEXT_MUTED']};
        background: #202631;
        border-color: #303847;
    }}
    QPushButton#QuietButton, QToolButton#DisclosureButton {{
        color: #bdc7d7;
        border-color: transparent;
        background: transparent;
    }}
    QPushButton#QuietButton:hover, QToolButton#DisclosureButton:hover {{
        color: {t['TEXT']};
        background: rgba(122, 162, 255, 0.06);
        border-color: transparent;
    }}
    QToolButton#DisclosureButton {{
        min-height: 34px;
        padding: 0 4px;
        text-align: left;
        font-weight: 600;
    }}
    QPushButton#StopButton {{ color: #f1d58a; border-color: #65583a; }}
    QRadioButton, QCheckBox {{ spacing: 9px; min-height: 28px; }}
    QRadioButton::indicator, QCheckBox::indicator {{ width: 17px; height: 17px; }}
    QProgressBar {{
        min-height: 13px;
        max-height: 13px;
        background: #202735;
        border: none;
        border-radius: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {t['PRIMARY']}; border-radius: 6px; }}
    QTableWidget {{
        background: #151a22;
        alternate-background-color: #1b212c;
        border: 1px solid #293240;
        border-radius: 9px;
        gridline-color: #293240;
        selection-background-color: #31466f;
    }}
    QHeaderView::section {{
        background: #202735;
        color: #aeb9ca;
        padding: 8px;
        border: none;
        border-right: 1px solid #303847;
        font-weight: 600;
    }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ width: 9px; background: transparent; }}
    QScrollBar::handle:vertical {{
        min-height: 36px;
        background: #343e4e;
        border-radius: 4px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


def _label(text: str, object_name: str | None = None, *, word_wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(word_wrap)
    return label


def _primary(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("PrimaryButton")
    button.setProperty("primaryAction", True)
    return button


def _quiet(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("QuietButton")
    return button


class PremiumBanner(QFrame):
    """Simple message surface without selectable-text focus chrome."""

    def __init__(self, text: str = "", kind: str = "info") -> None:
        super().__init__()
        self.setObjectName("PremiumBanner")
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.addWidget(self.label)
        self.set_message(text, kind)

    def set_message(self, text: str, kind: str = "info") -> None:
        color = {
            "success": TOKENS["SUCCESS"],
            "warning": TOKENS["WARNING"],
            "error": TOKENS["ERROR"],
            "info": TOKENS["PRIMARY"],
        }.get(kind, TOKENS["PRIMARY"])
        self.label.setText(text)
        self.setStyleSheet(
            "QFrame#PremiumBanner {"
            f"background: {TOKENS['SURFACE_ALT']}; border: 1px solid {color}; "
            "border-radius: 8px; }"
            "QFrame#PremiumBanner QLabel { background: transparent; border: none; }"
        )
        self.setVisible(bool(text))


def _banner() -> PremiumBanner:
    return PremiumBanner()


def _surface() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Surface")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(16)
    return frame, layout


def _header(eyebrow: str, title: str, subtitle: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    layout.addWidget(_label(eyebrow, "Eyebrow"))
    layout.addWidget(_label(title, "PageTitle"))
    layout.addWidget(_label(subtitle, "Subtitle", word_wrap=True))
    return widget


def _metric(number: str, caption: str) -> tuple[QWidget, QLabel]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(12, 9, 12, 9)
    layout.setSpacing(1)
    number_label = _label(number, "MetricNumber")
    number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    caption_label = _label(caption, "MetricLabel")
    caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(number_label)
    layout.addWidget(caption_label)
    return widget, number_label


def _configure_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)


class DisclosureSection(QFrame):
    """Compact progressive disclosure that only changes presentation."""

    def __init__(self, title: str, body: QWidget, *, expanded: bool = False) -> None:
        super().__init__()
        self.title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.button = QToolButton()
        self.button.setObjectName("DisclosureButton")
        self.button.setCheckable(True)
        self.button.clicked.connect(self.set_expanded)
        layout.addWidget(self.button)
        self.body = body
        layout.addWidget(body)
        self.set_expanded(expanded)

    @property
    def expanded(self) -> bool:
        return not self.body.isHidden()

    def set_title(self, title: str) -> None:
        self.title = title
        self.set_expanded(self.expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.button.setChecked(expanded)
        self.button.setText(("⌄  " if expanded else "›  ") + self.title)
        self.body.setVisible(expanded)


class ConfirmationDialog(QDialog):
    """Compact confirmation bound to an already reviewed immutable plan."""

    def __init__(
        self,
        *,
        parent: QWidget,
        plan: SignatureExecutionPlan,
        will_change: int,
        will_skip: int,
        ambiguous: int,
        partial: bool,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ConfirmationDialog")
        self.setStyleSheet(premium_stylesheet())
        self.setWindowTitle("确认修改")
        self.setModal(True)
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(15)
        layout.addWidget(_label("确认修改", "PageTitle"))
        rows = QGridLayout()
        rows.setHorizontalSpacing(28)
        rows.setVerticalSpacing(10)
        values = (
            ("旧文字", plan.rule.old_text),
            ("新文字", plan.rule.new_text),
            ("将修改", f"{will_change} 个 PSD"),
            ("不会修改", f"{will_skip} 个 PSD"),
            ("需确认（暂不处理）", f"{ambiguous} 个 PSD"),
        )
        for row, (caption, value) in enumerate(values):
            rows.addWidget(_label(caption, "Muted"), row, 0)
            rows.addWidget(_label(value, "FieldLabel", word_wrap=True), row, 1)
        rows.setColumnStretch(1, 1)
        layout.addLayout(rows)
        layout.addWidget(
            _label(
                "修改后的文件会保存到独立输出位置，原 PSD 不会被覆盖。",
                "SafetyText",
                word_wrap=True,
            )
        )
        self.partial_check = QCheckBox(
            f"我知道本次只处理这 {plan.selected_count} 个 PSD"
        )
        self.partial_check.setVisible(partial)
        layout.addWidget(self.partial_check)
        actions = QHBoxLayout()
        self.back_button = _quiet("返回")
        self.start_button = _primary("开始处理")
        self.start_button.setEnabled(not partial)
        self.back_button.clicked.connect(self.reject)
        self.start_button.clicked.connect(self.accept)
        self.partial_check.toggled.connect(self._refresh_start)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        actions.addWidget(self.start_button)
        layout.addLayout(actions)

    @property
    def partial_acknowledged(self) -> bool:
        return self.partial_check.isChecked()

    def _refresh_start(self) -> None:
        self.start_button.setEnabled(
            not self.partial_check.isVisible() or self.partial_check.isChecked()
        )


ConfirmationFactory = Callable[..., ConfirmationDialog]


class PremiumSimpleWindow(QMainWindow):
    """Public Premium Simple UI backed exclusively by WorkflowController."""

    DEFAULT_SIZE = (1160, 760)
    MINIMUM_SIZE = (940, 660)

    def __init__(
        self,
        *,
        controller: WorkflowController | None = None,
        auto_environment_check: bool = True,
        confirmation_factory: ConfirmationFactory = ConfirmationDialog,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("表情包 PSD 批量署名替换")
        self.resize(*self.DEFAULT_SIZE)
        self.setMinimumSize(*self.MINIMUM_SIZE)
        self.setFont(build_application_font())
        self.setStyleSheet(premium_stylesheet())
        self.controller = controller or WorkflowController(parent=self)
        self._confirmation_factory = confirmation_factory
        self._output_mode = "AUTO"
        self._setting_auto_output = False
        self._resetting = False
        self._active_operation: str | None = None
        self._allow_close = False
        self._close_when_finished = False
        self._inspect_result: InspectRunResult | None = None
        self._reviewed_plan: SignatureExecutionPlan | None = None
        self._reviewed_plan_id = ""
        self._reviewed_generation = -1
        self._selected_old_text = ""
        self._text_items: dict[str, tuple[InspectItem, ...]] = {}
        self._execute_counts = {"success": 0, "skipped": 0, "failed": 0}

        root = QWidget()
        root.setObjectName("PremiumRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_top_bar())

        self.main_scroll = QScrollArea()
        self.main_scroll.setObjectName("MainViewport")
        self.main_scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("MainBody")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(34, 24, 34, 24)
        body_layout.addStretch(1)
        self.stack = QStackedWidget()
        self.stack.setObjectName("PrimaryContent")
        self.stack.setMaximumWidth(960)
        body_layout.addWidget(self.stack, 12)
        body_layout.addStretch(1)
        self.main_scroll.setWidget(body)
        root_layout.addWidget(self.main_scroll, 1)

        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(34, 8, 34, 12)
        footer_layout.addWidget(_label("完全本地处理 · 输入目录只读 · 没有遥测", "FooterText"))
        footer_layout.addStretch(1)
        root_layout.addWidget(footer)

        self.pages: dict[PremiumPage, QWidget] = {}
        self._build_pages()
        self._connect_controller()
        self.set_page(PremiumPage.SETUP)
        self._on_busy(False, "")
        if auto_environment_check:
            QTimer.singleShot(0, self._safe_environment_check)

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(34, 14, 34, 14)
        layout.setSpacing(14)
        layout.addWidget(_label("表情包 PSD 批量署名替换", "Brand"))
        self.version_label = _label(f"v{__version__}", "Version")
        layout.addWidget(self.version_label)
        layout.addStretch(1)
        self.photoshop_pill = _label("●  Photoshop 尚未检查", "ConnectionPill")
        self.photoshop_pill.setProperty("available", "unknown")
        layout.addWidget(self.photoshop_pill)
        self.help_button = _quiet("使用说明")
        self.help_button.setMaximumWidth(92)
        self.help_button.clicked.connect(self._open_help)
        layout.addWidget(self.help_button)
        return bar

    def _page(self, page_id: PremiumPage) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("PremiumPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        self.pages[page_id] = page
        self.stack.addWidget(page)
        return page, layout

    def _build_pages(self) -> None:
        self._build_setup_page()
        self._build_selection_page()
        self._build_preview_page()
        self._build_executing_page()
        self._build_result_page()
        self._build_fatal_page()

    def _build_setup_page(self) -> None:
        _page, layout = self._page(PremiumPage.SETUP)
        layout.addWidget(
            _header(
                "开始",
                "选择需要处理的 PSD",
                "只需选择素材位置，我们会先检查内容，不会直接修改文件。",
            )
        )
        surface, form = _surface()
        form.addWidget(_label("原 PSD 文件夹", "FieldLabel"))
        self.input_picker = PathPicker("例如 C:\\PSD素材", "选择 PSD 输入目录")
        form.addWidget(self.input_picker)
        output_header = QHBoxLayout()
        output_header.addWidget(_label("输出位置", "FieldLabel"))
        output_header.addStretch(1)
        self.output_mode_label = _label("自动建议", "Muted")
        output_header.addWidget(self.output_mode_label)
        self.restore_auto_button = _quiet("恢复自动建议")
        self.restore_auto_button.setVisible(False)
        self.restore_auto_button.clicked.connect(self._restore_auto_output)
        output_header.addWidget(self.restore_auto_button)
        form.addLayout(output_header)
        self.output_picker = PathPicker("请选择独立输出目录", "选择独立输出目录")
        form.addWidget(self.output_picker)
        self.output_hint = _label(
            "选择输入目录后会建议同级输出位置，但不会立即创建文件夹。",
            "SafetyText",
            word_wrap=True,
        )
        form.addWidget(self.output_hint)

        advanced_body = QWidget()
        advanced_layout = QGridLayout(advanced_body)
        advanced_layout.setContentsMargins(2, 2, 2, 2)
        advanced_layout.setHorizontalSpacing(12)
        advanced_layout.setVerticalSpacing(10)
        self.recursive_check = QCheckBox("同时检查子文件夹")
        self.recursive_check.setChecked(False)
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1, 100000)
        self.max_files_spin.setValue(100)
        self.max_files_spin.setSuffix(" 个 PSD")
        self.include_edit = QLineEdit("*.psd")
        advanced_layout.addWidget(self.recursive_check, 0, 0, 1, 2)
        advanced_layout.addWidget(_label("处理上限", "FieldLabel"), 1, 0)
        advanced_layout.addWidget(self.max_files_spin, 1, 1)
        advanced_layout.addWidget(_label("文件筛选", "FieldLabel"), 2, 0)
        advanced_layout.addWidget(self.include_edit, 2, 1)
        advanced_layout.setColumnStretch(1, 1)
        self.advanced_disclosure = DisclosureSection("高级设置", advanced_body)
        form.addWidget(self.advanced_disclosure)
        self.setup_banner = _banner()
        form.addWidget(self.setup_banner)
        self.inspect_button = _primary("检查 PSD")
        self.inspect_button.clicked.connect(self._start_inspect)
        form.addWidget(self.inspect_button)
        layout.addWidget(surface)
        layout.addStretch(1)

        self.input_picker.path_changed.connect(self._on_input_changed)
        self.output_picker.path_changed.connect(self._on_output_changed)
        self.recursive_check.toggled.connect(self._on_setup_option_changed)
        self.max_files_spin.valueChanged.connect(self._on_setup_option_changed)
        self.include_edit.textChanged.connect(self._on_setup_option_changed)

    def _build_selection_page(self) -> None:
        _page, layout = self._page(PremiumPage.TEXT_SELECTION)
        self.selection_header = _header(
            "检查完成",
            "已找到 0 个 PSD",
            "请选择要修改的文字，再填写新的署名。",
        )
        self.selection_title = self.selection_header.findChild(QLabel, "PageTitle")
        layout.addWidget(self.selection_header)
        surface, content = _surface()
        self.inspect_banner = _banner()
        content.addWidget(self.inspect_banner)
        content.addWidget(_label("请选择要修改的文字", "FieldLabel"))
        self.choice_container = QWidget()
        self.choice_layout = QVBoxLayout(self.choice_container)
        self.choice_layout.setContentsMargins(0, 0, 0, 0)
        self.choice_layout.setSpacing(8)
        content.addWidget(self.choice_container)
        self.choice_group = QButtonGroup(self)
        self.choice_group.setExclusive(True)
        content.addWidget(_label("新的署名", "FieldLabel"))
        self.new_text_edit = QLineEdit()
        self.new_text_edit.setPlaceholderText("输入替换后的文字")
        content.addWidget(self.new_text_edit)

        layer_body = QWidget()
        layer_layout = QVBoxLayout(layer_body)
        layer_layout.setContentsMargins(0, 0, 0, 0)
        layer_layout.setSpacing(8)
        layer_layout.addWidget(
            _label(
                "如需缩小匹配范围，可选择一个全局精确图层名；不选择时由预览安全判断。",
                "Muted",
                word_wrap=True,
            )
        )
        self.layer_name_combo = QComboBox()
        self.layer_name_combo.addItem("不限定图层名", None)
        layer_layout.addWidget(self.layer_name_combo)
        self.layer_table = QTableWidget(0, 4)
        self.layer_table.setHorizontalHeaderLabels(("PSD", "图层名", "图层路径", "当前文字"))
        _configure_table(self.layer_table)
        self.layer_table.setMinimumHeight(140)
        layer_layout.addWidget(self.layer_table)
        self.layer_disclosure = DisclosureSection("查看并选择具体图层", layer_body)
        self.layer_disclosure.setVisible(False)
        content.addWidget(self.layer_disclosure)
        self.rule_banner = _banner()
        content.addWidget(self.rule_banner)
        actions = QHBoxLayout()
        self.back_to_setup_button = _quiet("返回")
        self.back_to_setup_button.clicked.connect(lambda: self.set_page(PremiumPage.SETUP))
        actions.addWidget(self.back_to_setup_button)
        actions.addStretch(1)
        self.plan_button = _primary("查看修改预览")
        self.plan_button.clicked.connect(self._start_plan)
        actions.addWidget(self.plan_button)
        content.addLayout(actions)
        layout.addWidget(surface)
        layout.addStretch(1)
        self.new_text_edit.textChanged.connect(self._on_rule_changed)
        self.layer_name_combo.currentIndexChanged.connect(self._on_rule_changed)

    def _build_summary_strip(self) -> tuple[QFrame, dict[str, QLabel]]:
        strip = QFrame()
        strip.setObjectName("SummaryStrip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(0)
        labels: dict[str, QLabel] = {}
        for index, (key, caption) in enumerate(
            (("change", "将修改"), ("skip", "不会修改"), ("ambiguous", "需确认（暂不处理）"))
        ):
            widget, number = _metric("0", caption)
            labels[key] = number
            row.addWidget(widget, 1)
            if index < 2:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.VLine)
                divider.setStyleSheet("color: #2c3441;")
                row.addWidget(divider)
        return strip, labels

    def _build_preview_page(self) -> None:
        _page, layout = self._page(PremiumPage.PREVIEW)
        layout.setSpacing(14)
        layout.addWidget(
            _header("准备完成", "修改预览", "先看清本次会发生什么，再决定是否继续。")
        )
        strip, self.preview_metrics = self._build_summary_strip()
        layout.addWidget(strip)
        self.preview_banner = _banner()
        layout.addWidget(self.preview_banner)
        layout.addWidget(
            _label(
                "修改只会写入新的 PSD 副本，原文件保持不变。",
                "SafetyText",
                word_wrap=True,
            )
        )
        self.preview_error_line = _label("", "ErrorLine", word_wrap=True)
        self.preview_error_line.setVisible(False)
        layout.addWidget(self.preview_error_line)
        details_body = QWidget()
        details_layout = QVBoxLayout(details_body)
        details_layout.setContentsMargins(0, 0, 0, 0)
        self.plan_table = QTableWidget(0, 5)
        self.plan_table.setHorizontalHeaderLabels(("PSD", "结果", "原因", "图层", "输出位置"))
        _configure_table(self.plan_table)
        self.plan_table.setFixedHeight(220)
        details_layout.addWidget(self.plan_table)
        self.preview_details = DisclosureSection("查看详细列表", details_body)
        layout.addWidget(self.preview_details)
        actions = QHBoxLayout()
        self.back_to_selection_button = _quiet("返回修改")
        self.back_to_selection_button.clicked.connect(self._return_to_selection)
        actions.addWidget(self.back_to_selection_button)
        actions.addStretch(1)
        self.confirm_button = _primary("确认并开始处理")
        self.confirm_button.clicked.connect(self._confirm_and_execute)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)
        layout.addStretch(1)

    def _build_executing_page(self) -> None:
        _page, layout = self._page(PremiumPage.EXECUTING)
        layout.addWidget(
            _header("处理中", "正在处理素材", "你可以放心等待，原 PSD 不会被覆盖。")
        )
        surface, content = _surface()
        progress_row = QHBoxLayout()
        self.progress_count_label = _label("0 / 0", "FieldLabel")
        self.progress_percent_label = _label("0%", "FieldLabel")
        progress_row.addWidget(self.progress_count_label)
        progress_row.addStretch(1)
        progress_row.addWidget(self.progress_percent_label)
        content.addLayout(progress_row)
        self.execute_progress = QProgressBar()
        self.execute_progress.setRange(0, 1)
        self.execute_progress.setValue(0)
        self.execute_progress.setTextVisible(False)
        content.addWidget(self.execute_progress)
        content.addSpacing(8)
        content.addWidget(_label("正在处理", "Muted"))
        self.current_file_label = _label("准备中", "PageTitle")
        content.addWidget(self.current_file_label)
        execute_strip = QFrame()
        execute_strip.setObjectName("SummaryStrip")
        execute_row = QHBoxLayout(execute_strip)
        self.execute_metrics: dict[str, QLabel] = {}
        for key, caption in (("success", "成功"), ("skipped", "跳过"), ("failed", "失败")):
            widget, number = _metric("0", caption)
            self.execute_metrics[key] = number
            execute_row.addWidget(widget, 1)
        content.addWidget(execute_strip)
        self.cancel_button = _quiet("当前文件完成后停止")
        self.cancel_button.setObjectName("StopButton")
        self.cancel_button.clicked.connect(self._request_cancel)
        content.addWidget(self.cancel_button, 0, Qt.AlignmentFlag.AlignLeft)
        running_body = QWidget()
        running_layout = QVBoxLayout(running_body)
        running_layout.setContentsMargins(0, 0, 0, 0)
        self.running_detail_label = _label("尚无详细信息", "Muted", word_wrap=True)
        running_layout.addWidget(self.running_detail_label)
        self.executing_details = DisclosureSection("查看详细信息", running_body)
        content.addWidget(self.executing_details)
        self.execute_banner = _banner()
        content.addWidget(self.execute_banner)
        layout.addWidget(surface)
        layout.addStretch(1)

    def _build_result_page(self) -> None:
        _page, layout = self._page(PremiumPage.RESULT)
        self.result_header = _header("完成", "处理完成", "新的 PSD 副本已经保存到独立输出位置。")
        self.result_title = self.result_header.findChild(QLabel, "PageTitle")
        self.result_subtitle = self.result_header.findChild(QLabel, "Subtitle")
        layout.addWidget(self.result_header)
        surface, content = _surface()
        self.result_icon = _label("✓", "SuccessIcon")
        self.result_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.result_icon)
        self.result_large_number = _label("0", "LargeNumber")
        self.result_large_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.result_large_number)
        self.result_large_caption = _label("成功修改", "FieldLabel")
        self.result_large_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.result_large_caption)
        result_strip = QFrame()
        result_strip.setObjectName("SummaryStrip")
        result_row = QHBoxLayout(result_strip)
        self.result_metrics: dict[str, QLabel] = {}
        for key, caption in (("success", "成功"), ("skipped", "安全跳过"), ("failed", "失败")):
            widget, number = _metric("0", caption)
            self.result_metrics[key] = number
            result_row.addWidget(widget, 1)
        content.addWidget(result_strip)
        self.result_accounting = _label("", "Muted", word_wrap=True)
        content.addWidget(self.result_accounting)
        self.result_banner = _banner()
        content.addWidget(self.result_banner)
        result_detail_body = QWidget()
        result_detail_layout = QVBoxLayout(result_detail_body)
        result_detail_layout.setContentsMargins(0, 0, 0, 0)
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(("PSD", "结果", "说明"))
        _configure_table(self.result_table)
        self.result_table.setFixedHeight(160)
        result_detail_layout.addWidget(self.result_table)
        self.open_formal_report_button = _quiet("无可用正式报告")
        self.open_formal_report_button.setEnabled(False)
        self.open_formal_report_button.clicked.connect(self._open_formal_report)
        result_detail_layout.addWidget(self.open_formal_report_button)
        self.copy_diagnostic_button = _quiet("复制安全诊断")
        self.copy_diagnostic_button.clicked.connect(self._copy_diagnostic)
        result_detail_layout.addWidget(self.copy_diagnostic_button)
        self.result_details = DisclosureSection("查看详情", result_detail_body)
        content.addWidget(self.result_details)
        self.result_primary_button = _primary("打开输出文件夹")
        self.result_primary_button.clicked.connect(self._result_primary_action)
        content.addWidget(self.result_primary_button)
        self.new_task_button = _quiet("开始新任务")
        self.new_task_button.clicked.connect(self._new_task)
        content.addWidget(self.new_task_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(surface)
        layout.addStretch(1)
        self._result_primary_mode = "output"

    def _build_fatal_page(self) -> None:
        _page, layout = self._page(PremiumPage.FATAL)
        layout.addWidget(
            _header(
                "需要重新检查",
                "本次任务没有继续执行",
                "为了避免实际处理和预览不一致，本次没有继续。",
            )
        )
        surface, content = _surface()
        icon = _label("●", "FailureIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(icon)
        content.addWidget(
            _label(
                "为了避免使用失效的旧计划，请重新检查 PSD 后再试。",
                "SafetyText",
                word_wrap=True,
            )
        )
        self.fatal_message = _banner()
        content.addWidget(self.fatal_message)
        self.fatal_button = _primary("返回重新检查")
        self.fatal_button.clicked.connect(self._recover_from_fatal)
        content.addWidget(self.fatal_button)
        layout.addWidget(surface)
        layout.addStretch(1)

    def _connect_controller(self) -> None:
        self.controller.state_changed.connect(self._on_controller_state)
        self.controller.busy_changed.connect(self._on_busy)
        self.controller.environment_ready.connect(self._on_environment)
        self.controller.inspect_ready.connect(self.show_inspect_result)
        self.controller.plan_ready.connect(self.show_plan_result)
        self.controller.execution_ready.connect(self.show_execution_result)
        self.controller.event_received.connect(self._on_event)
        self.controller.failed.connect(self._on_failure)
        self.controller.job_finished.connect(self._on_job_finished)

    def set_page(self, page: PremiumPage) -> None:
        self.current_page = page
        current = self.pages[page]
        self.stack.setCurrentWidget(current)
        if current.layout() is not None:
            current.layout().activate()
        self.stack.setMinimumHeight(max(520, current.sizeHint().height()))
        self.main_scroll.verticalScrollBar().setValue(0)
        self._refresh_actions()

    def current_primary_buttons(self) -> list[QPushButton]:
        page = self.stack.currentWidget()
        return [
            button
            for button in page.findChildren(QPushButton)
            if button.property("primaryAction") and button.isVisibleTo(page)
        ]

    def current_visible_text(self) -> str:
        page = self.stack.currentWidget()
        values: list[str] = []
        for widget_type in (QLabel, QPushButton, QToolButton, QCheckBox, QRadioButton):
            for widget in page.findChildren(widget_type):
                if widget.isVisibleTo(page):
                    values.append(widget.text())
        return "\n".join(values)

    @property
    def output_mode(self) -> str:
        return self._output_mode

    def _on_input_changed(self, _value: str) -> None:
        if self._resetting or self.controller.busy:
            return
        if self._output_mode == "AUTO":
            suggestion = suggest_sibling_output(self.input_picker.path)
            self._setting_auto_output = True
            try:
                self.output_picker.set_path(suggestion or "")
            finally:
                self._setting_auto_output = False
            self.output_hint.setText(
                "已建议同级输出位置，但不会立即创建文件夹。"
                if suggestion
                else "请手动选择与输入目录互不包含的独立输出位置。"
            )
        self._invalidate_setup()

    def _on_output_changed(self, _value: str) -> None:
        if self._resetting or self.controller.busy:
            return
        if not self._setting_auto_output:
            self._output_mode = "MANUAL"
            self.output_mode_label.setText("手动设置")
            self.restore_auto_button.setVisible(True)
        self._invalidate_setup()

    def _restore_auto_output(self) -> None:
        if self.controller.busy:
            return
        self._output_mode = "AUTO"
        self.output_mode_label.setText("自动建议")
        self.restore_auto_button.setVisible(False)
        suggestion = suggest_sibling_output(self.input_picker.path)
        self._setting_auto_output = True
        try:
            self.output_picker.set_path(suggestion or "")
        finally:
            self._setting_auto_output = False
        self.output_hint.setText(
            "已建议同级输出位置，但不会立即创建文件夹。"
            if suggestion
            else "请手动选择与输入目录互不包含的独立输出位置。"
        )
        self._invalidate_setup()

    def _on_setup_option_changed(self, *_args) -> None:
        if not self._resetting and not self.controller.busy:
            self._invalidate_setup()

    def _invalidate_setup(self) -> None:
        had_review = self.controller.inspect_result is not None or self.controller.plan is not None
        self.controller.invalidate_setup()
        self._clear_review_data()
        if had_review:
            self.setup_banner.set_message("设置发生了变化，请重新检查 PSD。", "warning")
        self.set_page(PremiumPage.SETUP)

    def _clear_review_data(self) -> None:
        self._inspect_result = None
        self._reviewed_plan = None
        self._reviewed_plan_id = ""
        self._reviewed_generation = -1
        self._selected_old_text = ""
        self._text_items = {}
        self._clear_choice_rows()
        self.plan_table.setRowCount(0)
        self.result_table.setRowCount(0)

    def _clear_choice_rows(self) -> None:
        for button in self.choice_group.buttons():
            self.choice_group.removeButton(button)
        while self.choice_layout.count():
            item = self.choice_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _safe_environment_check(self) -> None:
        if self.controller.busy:
            return
        self._active_operation = "environment"
        try:
            self.controller.check_environment()
        except RuntimeError:
            self._active_operation = None

    def _start_inspect(self) -> None:
        if self.controller.busy:
            return
        try:
            options = self.controller.make_options(
                self.input_picker.path,
                self.output_picker.path,
                recursive=self.recursive_check.isChecked(),
                include=self.include_edit.text(),
                max_files=self.max_files_spin.value(),
            )
            self._active_operation = "inspect"
            self.setup_banner.set_message("")
            self.controller.start_inspect(options)
        except (ValueError, RuntimeError) as error:
            self._active_operation = None
            self.setup_banner.set_message(str(error), "error")

    def show_inspect_result(self, result: InspectRunResult) -> None:
        self._inspect_result = result
        by_text: dict[str, list[InspectItem]] = defaultdict(list)
        for item in result.items:
            if item.document_opened and item.current_text:
                by_text[item.current_text].append(item)
        self._text_items = {key: tuple(value) for key, value in by_text.items()}
        self._populate_text_choices()
        self.selection_title.setText(f"已找到 {result.candidate_count} 个 PSD")
        if result.cancelled or not result.planned_items_complete:
            self.inspect_banner.set_message(
                "检查没有完整完成，暂时不能生成修改预览；请返回重新检查。",
                "warning",
            )
        elif result.max_files_reached or result.unplanned_count:
            self.inspect_banner.set_message(
                f"本次只检查了前 {result.selected_count} 个 PSD，"
                f"还有 {result.unplanned_count} 个未纳入。",
                "warning",
            )
        elif not self._text_items:
            self.inspect_banner.set_message("没有找到可编辑文字图层。", "warning")
        else:
            self.inspect_banner.set_message(
                f"已检查 {result.processed_count} 个 PSD，请选择要修改的文字。",
                "success",
            )
        self.set_page(PremiumPage.TEXT_SELECTION)
        self._refresh_actions()

    def _populate_text_choices(self) -> None:
        self._resetting = True
        try:
            self._clear_choice_rows()
            self._selected_old_text = ""
            ranked = sorted(
                self._text_items.items(),
                key=lambda pair: (-len({item.relative_path for item in pair[1]}), pair[0]),
            )
            for index, (text, items) in enumerate(ranked):
                row = QFrame()
                row.setObjectName("ChoiceRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(15, 9, 15, 9)
                radio = QRadioButton(text)
                count = len({item.relative_path for item in items})
                row_layout.addWidget(radio, 1)
                row_layout.addWidget(_label(f"{count} 个文件", "Muted"))
                self.choice_group.addButton(radio)
                radio.toggled.connect(
                    lambda checked, value=text, frame=row: self._on_text_choice(
                        value, frame, checked
                    )
                )
                self.choice_layout.addWidget(row)
                if index == 0:
                    radio.setChecked(True)
        finally:
            self._resetting = False
        if ranked:
            self._selected_old_text = ranked[0][0]
            self._update_layer_details()

    def _on_text_choice(self, value: str, row: QFrame, checked: bool) -> None:
        row.setProperty("selected", checked)
        row.style().unpolish(row)
        row.style().polish(row)
        if not checked:
            return
        changed = value != self._selected_old_text
        self._selected_old_text = value
        self._update_layer_details()
        if changed and not self._resetting:
            self._invalidate_rule()
        self._refresh_actions()

    def _update_layer_details(self) -> None:
        items = self._text_items.get(self._selected_old_text, ())
        names = sorted({item.layer_name for item in items if item.layer_name})
        per_file: dict[str, int] = defaultdict(int)
        for item in items:
            per_file[item.relative_path] += 1
        needs_detail = len(names) > 1 or any(count > 1 for count in per_file.values())
        self.layer_disclosure.setVisible(needs_detail)
        if needs_detail:
            self.layer_disclosure.set_title("有一些文件可能需要指定具体图层 · 查看并选择")
        self.layer_name_combo.blockSignals(True)
        self.layer_name_combo.clear()
        self.layer_name_combo.addItem("不限定图层名", None)
        for name in names:
            self.layer_name_combo.addItem(name, name)
        self.layer_name_combo.blockSignals(False)
        self.layer_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (
                PurePosixPath(item.relative_path).name,
                item.layer_name or "—",
                item.layer_path or "—",
                item.current_text,
            )
            for column, value in enumerate(values):
                self.layer_table.setItem(row, column, QTableWidgetItem(str(value)))
        if items:
            self.layer_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _on_rule_changed(self, *_args) -> None:
        if not self._resetting and not self.controller.busy:
            self._invalidate_rule()
        self._refresh_actions()

    def _invalidate_rule(self) -> None:
        had_plan = self.controller.plan is not None
        self.controller.invalidate_rule()
        self._reviewed_plan = None
        self._reviewed_plan_id = ""
        self._reviewed_generation = -1
        if had_plan:
            self.rule_banner.set_message("文字或图层设置发生了变化，请重新查看修改预览。", "warning")
            self.set_page(PremiumPage.TEXT_SELECTION)

    def _start_plan(self) -> None:
        if self.controller.busy:
            return
        try:
            layer_name = self.layer_name_combo.currentData()
            rule = SignatureRule(
                old_text=self._selected_old_text,
                new_text=self.new_text_edit.text(),
                layer_name=layer_name if isinstance(layer_name, str) else None,
            )
            self._active_operation = "plan"
            self.rule_banner.set_message("")
            self.controller.start_plan(rule)
        except (ValueError, RuntimeError) as error:
            self._active_operation = None
            self.rule_banner.set_message(str(error), "error")

    @staticmethod
    def _plan_counts(items: tuple[PlanItem, ...]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            counts[item.decision] += 1
        return dict(counts)

    def show_plan_result(self, result: PlanRunResult) -> None:
        plan = result.plan if result.planned_items_complete else None
        self._reviewed_plan = plan
        self._reviewed_plan_id = plan.plan_id if plan is not None else ""
        self._reviewed_generation = self.controller.plan_generation
        counts = self._plan_counts(result.items)
        will_change = counts.get("WOULD_REPLACE", 0)
        will_skip = counts.get("SKIP_NO_MATCH", 0) + counts.get("SKIP_EXISTS", 0)
        ambiguous = counts.get("SKIP_AMBIGUOUS", 0)
        errors = counts.get("ERROR", 0)
        self.preview_metrics["change"].setText(str(will_change))
        self.preview_metrics["skip"].setText(str(will_skip))
        self.preview_metrics["ambiguous"].setText(str(ambiguous))
        if ambiguous:
            self.preview_banner.set_message(
                "存在多个可能文字图层的文件会暂不处理，你可以先处理其他安全项目。",
                "warning",
            )
        elif result.partial_plan:
            self.preview_banner.set_message(
                f"本次只包含 {result.selected_count} 个 PSD，"
                f"还有 {result.unplanned_count} 个没有进入本次处理。",
                "warning",
            )
        elif plan is None:
            self.preview_banner.set_message("设置或文件发生变化，请重新检查 PSD。", "error")
        else:
            self.preview_banner.set_message("预览已准备好，请核对后再开始处理。", "success")
        self.preview_error_line.setVisible(errors > 0)
        self.preview_error_line.setText(
            f"有 {errors} 个文件暂时无法处理。请展开详细列表查看安全错误类别。"
            if errors
            else ""
        )
        self._populate_plan_table(result.items, plan)
        self.preview_details.set_expanded(False)
        self.set_page(PremiumPage.PREVIEW)
        self._refresh_actions()

    def _populate_plan_table(
        self,
        items: tuple[PlanItem, ...],
        plan: SignatureExecutionPlan | None,
    ) -> None:
        labels = {
            "WOULD_REPLACE": "将修改",
            "SKIP_NO_MATCH": "不会修改",
            "SKIP_EXISTS": "不会修改",
            "SKIP_AMBIGUOUS": "需确认（暂不处理）",
            "ERROR": "暂时无法处理",
        }
        reasons = {
            "WOULD_REPLACE": "找到唯一文字",
            "SKIP_NO_MATCH": "没有找到所选文字",
            "SKIP_EXISTS": "输出位置已有文件",
            "SKIP_AMBIGUOUS": "发现多个可能文字图层",
            "ERROR": "检查时遇到错误",
        }
        layer_name = plan.rule.layer_name if plan is not None else None
        self.plan_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = (
                PurePosixPath(item.relative_path).name,
                labels.get(item.decision, "暂不处理"),
                item.error_code or reasons.get(item.decision, "请查看结果"),
                layer_name or "不限定",
                item.output_relative_path or "—",
            )
            for column, value in enumerate(values):
                self.plan_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.plan_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def _return_to_selection(self) -> None:
        if self.controller.busy:
            return
        self.controller.invalidate_rule()
        self._reviewed_plan = None
        self._reviewed_plan_id = ""
        self._reviewed_generation = -1
        self.set_page(PremiumPage.TEXT_SELECTION)

    def _confirm_and_execute(self) -> None:
        if self.controller.busy or self.controller.state is not GuiState.DRY_RUN_REVIEW:
            return
        plan = self._reviewed_plan
        result = self.controller.plan_result
        if plan is None or result is None:
            self.preview_banner.set_message("设置或文件发生变化，请重新预览。", "error")
            self._refresh_actions()
            return
        counts = self._plan_counts(result.items)
        dialog = self._confirmation_factory(
            parent=self,
            plan=plan,
            will_change=counts.get("WOULD_REPLACE", 0),
            will_skip=counts.get("SKIP_NO_MATCH", 0) + counts.get("SKIP_EXISTS", 0),
            ambiguous=counts.get("SKIP_AMBIGUOUS", 0),
            partial=result.partial_plan,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.controller.confirm_current_plan(
                expected_plan=plan,
                expected_plan_id=self._reviewed_plan_id,
                expected_generation=self._reviewed_generation,
                review_acknowledged=True,
                partial_acknowledged=dialog.partial_acknowledged,
            )
            self._active_operation = "execute"
            self.controller.start_execute()
        except RuntimeError:
            if self.controller.state is GuiState.USER_CONFIRMED:
                self.controller.revoke_confirmation()
            if self.controller.state is GuiState.SETUP and self.controller.plan is None:
                self._show_fatal("正式处理未能安全开始，请重新检查 PSD。")
            else:
                self.preview_banner.set_message(
                    "确认状态已经变化，请重新核对修改预览。",
                    "error",
                )
                self.set_page(PremiumPage.PREVIEW)
            self._refresh_actions()

    def _on_controller_state(self, state: GuiState) -> None:
        if state is GuiState.EXECUTING:
            self.set_page(PremiumPage.EXECUTING)
        self._refresh_actions()

    def _on_busy(self, busy: bool, _label: str) -> None:
        for widget in (
            self.input_picker,
            self.output_picker,
            self.restore_auto_button,
            self.recursive_check,
            self.max_files_spin,
            self.include_edit,
            self.new_text_edit,
            self.layer_name_combo,
            self.back_to_setup_button,
            self.back_to_selection_button,
        ):
            widget.setEnabled(not busy)
        for button in self.choice_group.buttons():
            button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        busy = self.controller.busy
        self.inspect_button.setEnabled(not busy)
        inspect_ready = (
            self.controller.inspect_result is not None
            and self.controller.inspect_result.planned_items_complete
        )
        self.plan_button.setEnabled(
            not busy
            and inspect_ready
            and bool(self._selected_old_text)
            and bool(self.new_text_edit.text())
            and self.new_text_edit.text() != self._selected_old_text
        )
        self.confirm_button.setEnabled(
            not busy
            and self.controller.state is GuiState.DRY_RUN_REVIEW
            and self.controller.plan is self._reviewed_plan
            and self._reviewed_plan is not None
        )

    def _on_environment(self, result: EnvironmentCheckResult) -> None:
        self.photoshop_pill.setProperty("available", "true" if result.available else "false")
        if result.available:
            version = f" {result.version}" if result.version else ""
            self.photoshop_pill.setText(f"●  Photoshop 已连接{version}")
        else:
            self.photoshop_pill.setText("●  Photoshop 未连接")
        self.photoshop_pill.style().unpolish(self.photoshop_pill)
        self.photoshop_pill.style().polish(self.photoshop_pill)

    def _on_event(self, event: WorkflowEvent) -> None:
        if event.phase is not WorkflowPhase.EXECUTION:
            return
        total = max(1, event.total)
        value = min(max(0, event.index), total)
        self.execute_progress.setRange(0, total)
        self.execute_progress.setValue(value)
        self.progress_count_label.setText(f"{event.index} / {event.total}")
        self.progress_percent_label.setText(f"{round(value * 100 / total)}%")
        if event.kind is WorkflowEventKind.RUN_STARTED:
            self._execute_counts = {"success": 0, "skipped": 0, "failed": 0}
            self.current_file_label.setText("准备中")
            self.running_detail_label.setText("任务已开始，等待第一个文件。")
        elif event.kind is WorkflowEventKind.FILE_STARTED and event.relative_path:
            name = PurePosixPath(event.relative_path).name
            self.current_file_label.setText(name)
            self.running_detail_label.setText(f"正在处理：{name}")
        elif event.kind is WorkflowEventKind.FILE_RESULT and event.status:
            if event.status == "REPLACED":
                category = "success"
            elif event.status.startswith("SKIPPED"):
                category = "skipped"
            elif event.status.startswith("FAILED"):
                category = "failed"
            else:
                category = None
            if category:
                self._execute_counts[category] += 1
            for key, label in self.execute_metrics.items():
                label.setText(str(self._execute_counts[key]))

    def _request_cancel(self) -> None:
        self.controller.cancel()
        self.cancel_button.setEnabled(False)
        self.execute_banner.set_message(
            "正在安全停止：当前文件完成后不会继续处理下一个文件。",
            "warning",
        )

    def show_execution_result(self, result: ExecutionRunResult) -> None:
        self._execution_result = result
        success = sum(item.status == "REPLACED" for item in result.items)
        skipped = sum(item.status.startswith("SKIPPED") for item in result.items)
        failures = tuple(item for item in result.items if item.status.startswith("FAILED"))
        self.result_metrics["success"].setText(str(success))
        self.result_metrics["skipped"].setText(str(skipped))
        self.result_metrics["failed"].setText(str(len(failures)))
        self.result_large_number.setText(str(success))
        if result.stale or result.cancelled:
            self.result_accounting.setText(
                f"共发现 {result.candidate_count} 个 PSD，本次计划纳入 "
                f"{result.selected_count} 个；实际已完成 {result.processed_count} 个，"
                f"计划内还有 {result.remaining_count} 个没有继续；另有 "
                f"{result.unplanned_count} 个未纳入本次处理。"
            )
        else:
            self.result_accounting.setText(
                f"共发现 {result.candidate_count} 个 PSD，本次计划纳入 "
                f"{result.selected_count} 个；其余 {result.unplanned_count} 个"
                "未纳入本次处理。"
            )
        self._populate_result_table(result)
        self.result_details.set_expanded(bool(failures))
        if result.stale:
            self.result_title.setText("需要重新检查")
            self.result_subtitle.setText("为了避免实际处理和预览不一致，本次没有继续。")
            self.result_icon.setText("●")
            self.result_icon.setObjectName("FailureIcon")
            self.result_large_caption.setText("没有继续执行旧计划")
            self.result_banner.set_message("设置或文件发生了变化，请重新检查 PSD。", "error")
            self.result_primary_button.setText("返回重新检查")
            self._result_primary_mode = "recheck"
        elif result.cancelled:
            self.result_title.setText("任务已停止")
            self.result_subtitle.setText("已完成的安全结果会保留；未开始的文件没有继续处理。")
            self.result_icon.setText("■")
            self.result_icon.setObjectName("FailureIcon")
            self.result_large_caption.setText("成功修改")
            self.result_banner.set_message("已安全停止。", "warning")
            self.result_primary_button.setText("打开输出文件夹")
            self._result_primary_mode = "output"
        elif failures:
            self.result_title.setText(f"处理完成，但有 {len(failures)} 个文件需要查看")
            self.result_subtitle.setText("成功的输出已经保留；失败项目不会作为成功结果保留。")
            self.result_icon.setText("✓")
            self.result_icon.setObjectName("SuccessIcon")
            self.result_large_caption.setText("成功修改")
            self.result_banner.set_message(
                "失败输出已按安全清理规则处理，请在详情中查看错误类别。",
                "error",
            )
            self.result_primary_button.setText("打开输出文件夹")
            self._result_primary_mode = "output"
        else:
            self.result_title.setText("处理完成")
            self.result_subtitle.setText("新的 PSD 副本已经保存到独立输出位置。")
            self.result_icon.setText("✓")
            self.result_icon.setObjectName("SuccessIcon")
            self.result_large_caption.setText("成功修改")
            self.result_banner.set_message("原 PSD 保持不变。", "success")
            self.result_primary_button.setText("打开输出文件夹")
            self._result_primary_mode = "output"
        self.result_icon.style().unpolish(self.result_icon)
        self.result_icon.style().polish(self.result_icon)
        self._refresh_formal_report_action()
        self.set_page(PremiumPage.RESULT)

    def _populate_result_table(self, result: ExecutionRunResult) -> None:
        labels = {
            "REPLACED": "成功",
            "SKIPPED_NO_MATCH": "安全跳过",
            "SKIPPED_AMBIGUOUS": "需确认（暂不处理）",
            "SKIPPED_EXISTS": "安全跳过",
        }
        ordered_items = tuple(
            sorted(result.items, key=lambda item: (not item.status.startswith("FAILED"), item.relative_path))
        )
        self.result_table.setRowCount(len(ordered_items))
        for row, item in enumerate(ordered_items):
            if item.status.startswith("FAILED"):
                label = "失败"
                reason = self._safe_failure_reason(item.error_code)
            else:
                label = labels.get(item.status, "安全跳过")
                reason = {
                    "REPLACED": "已写入输出副本",
                    "SKIPPED_NO_MATCH": "没有找到所选文字",
                    "SKIPPED_AMBIGUOUS": "存在多个可能文字图层",
                    "SKIPPED_EXISTS": "输出文件已存在",
                }.get(item.status, item.error_code or "未处理")
            values = (PurePosixPath(item.relative_path).name, label, reason)
            for column, value in enumerate(values):
                self.result_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    @staticmethod
    def _safe_failure_reason(error_code: str | None) -> str:
        """Translate internal execution categories into restrained public wording."""

        code = (error_code or "").upper()
        if "LAYER_NAME" in code:
            return "图层名称未能安全保留"
        if "MATCH_CHANGED" in code:
            return "保存前文字匹配状态发生了变化"
        if "SAVE" in code:
            return "保存输出副本失败"
        if "PHOTOSHOP" in code or "COM" in code:
            return "Photoshop 处理未完成"
        return "处理未完成"

    def _refresh_formal_report_action(self) -> None:
        reference = self.controller.formal_report_ref
        if reference is None:
            self.open_formal_report_button.setText("无可用正式报告")
            self.open_formal_report_button.setEnabled(False)
            self.open_formal_report_button.setToolTip("")
            return
        exists = reference.summary_path.exists()
        self.open_formal_report_button.setText(
            "打开本次执行报告" if exists else "本次执行报告已不存在"
        )
        self.open_formal_report_button.setEnabled(exists)
        self.open_formal_report_button.setToolTip(str(reference.summary_path) if exists else "")

    def _result_primary_action(self) -> None:
        if self._result_primary_mode == "recheck":
            self._recover_from_fatal()
        else:
            self._open_output()

    def _open_output(self) -> None:
        plan = self.controller.plan
        if plan is None:
            self.result_banner.set_message("当前没有可确认的输出位置。", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(plan.options.output_dir)))

    def _open_formal_report(self) -> None:
        reference = self.controller.formal_report_ref
        if reference is None or not reference.summary_path.exists():
            self.result_banner.set_message("无可用正式报告。", "warning")
            self._refresh_formal_report_action()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(reference.summary_path)))

    def _copy_diagnostic(self) -> None:
        result = self.controller.execution_result
        if result is None:
            return
        diagnostic = build_public_diagnostic(result)
        QApplication.clipboard().setText(
            json.dumps(diagnostic, ensure_ascii=False, indent=2, sort_keys=True)
        )
        self.result_banner.set_message("已复制不含路径、文件名和文字的安全诊断。", "success")

    def _new_task(self) -> None:
        if self.controller.busy:
            return
        self.controller.invalidate_setup()
        self._clear_review_data()
        self.new_text_edit.clear()
        self.setup_banner.set_message("")
        self.set_page(PremiumPage.SETUP)

    def _show_fatal(self, message: str) -> None:
        self.result_details.set_expanded(False)
        self.preview_details.set_expanded(False)
        self.fatal_message.set_message(message, "error")
        self.set_page(PremiumPage.FATAL)

    def _recover_from_fatal(self) -> None:
        if self.controller.busy:
            return
        self.controller.invalidate_setup()
        self._clear_review_data()
        self.set_page(PremiumPage.SETUP)
        self.setup_banner.set_message("请重新检查 PSD。", "warning")

    def _on_failure(self, _code: str, _message: str) -> None:
        if self._active_operation == "execute":
            self._show_fatal("请重新检查 PSD 后再试。")
        elif self._active_operation == "plan":
            self.rule_banner.set_message(
                "修改预览没有生成，请重新检查设置后再试。",
                "error",
            )
            self.set_page(PremiumPage.TEXT_SELECTION)
        elif self._active_operation == "inspect":
            self.setup_banner.set_message(
                "PSD 检查没有完成，请确认 Photoshop 可用后再试。",
                "error",
            )
            self.set_page(PremiumPage.SETUP)

    def _on_job_finished(self) -> None:
        self._active_operation = None
        if self._close_when_finished:
            self._allow_close = True
            self.close()

    def _open_help(self) -> None:
        path = resolve_help_document()
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self,
                "使用说明",
                "请查看项目 README 和 docs/WINDOWS_PSD_SIGNATURE_GUIDE_CN.md。",
            )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._allow_close or not self.controller.busy:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "任务仍在运行",
            "现在关闭不会强制终止 Photoshop。是否请求在当前文件完成后停止？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer is QMessageBox.StandardButton.Yes:
            self._close_when_finished = True
            self._request_cancel()
        event.ignore()


__all__ = [
    "ConfirmationDialog",
    "DisclosureSection",
    "PremiumPage",
    "PremiumSimpleWindow",
    "premium_stylesheet",
    "resolve_help_document",
    "suggest_sibling_output",
]

"""One centralized dark theme for the Phase 2 GUI MVP."""

from __future__ import annotations

from PySide6.QtGui import QFont


TOKENS = {
    "BG": "#0f1117",
    "SURFACE": "#181c24",
    "SURFACE_ALT": "#202532",
    "TEXT": "#e7eaf0",
    "TEXT_MUTED": "#9aa4b2",
    "PRIMARY": "#7aa2ff",
    "PRIMARY_HOVER": "#93b4ff",
    "SUCCESS": "#45d483",
    "WARNING": "#ffd166",
    "ERROR": "#ff6b6b",
    "BORDER": "#303746",
}


def build_stylesheet() -> str:
    t = TOKENS
    return f"""
    * {{
        font-size: 13px;
        color: {t['TEXT']};
    }}
    QMainWindow, QWidget#Root {{ background: {t['BG']}; }}
    QWidget#TopBar, QWidget#StepRail, QWidget#JobBar,
    QFrame#Card, QGroupBox {{
        background: {t['SURFACE']};
        border: 1px solid {t['BORDER']};
        border-radius: 10px;
    }}
    QLabel#Title {{ font-size: 22px; font-weight: 700; }}
    QLabel#PageTitle {{ font-size: 20px; font-weight: 700; }}
    QLabel#Muted {{ color: {t['TEXT_MUTED']}; }}
    QLabel#SuccessText {{ color: {t['SUCCESS']}; font-weight: 600; }}
    QLabel#WarningText {{ color: {t['WARNING']}; font-weight: 600; }}
    QLabel#ErrorText {{ color: {t['ERROR']}; font-weight: 600; }}
    QLineEdit, QSpinBox, QComboBox {{
        min-height: 38px;
        padding: 0 10px;
        background: {t['SURFACE_ALT']};
        border: 1px solid {t['BORDER']};
        border-radius: 8px;
        selection-background-color: {t['PRIMARY']};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid {t['PRIMARY']};
    }}
    QPushButton, QToolButton {{
        min-height: 40px;
        padding: 0 16px;
        background: {t['SURFACE_ALT']};
        border: 1px solid {t['BORDER']};
        border-radius: 8px;
    }}
    QPushButton:hover, QToolButton:hover {{ border-color: {t['PRIMARY']}; }}
    QPushButton:disabled, QToolButton:disabled {{
        color: #667080;
        background: #171b23;
    }}
    QPushButton#PrimaryButton {{
        color: #0b1020;
        background: {t['PRIMARY']};
        border-color: {t['PRIMARY']};
        font-weight: 700;
    }}
    QPushButton#PrimaryButton:hover {{ background: {t['PRIMARY_HOVER']}; }}
    QPushButton#DangerButton {{ color: {t['ERROR']}; border-color: {t['ERROR']}; }}
    QPushButton#StepButton {{
        min-height: 44px;
        text-align: left;
        background: transparent;
        border-color: transparent;
    }}
    QPushButton#StepButton[active="true"] {{
        background: {t['SURFACE_ALT']};
        border-color: {t['PRIMARY']};
        color: {t['PRIMARY']};
        font-weight: 700;
    }}
    QTableView {{
        background: {t['SURFACE']};
        alternate-background-color: {t['SURFACE_ALT']};
        border: 1px solid {t['BORDER']};
        border-radius: 8px;
        gridline-color: {t['BORDER']};
        selection-background-color: #31466f;
        selection-color: {t['TEXT']};
    }}
    QHeaderView::section {{
        background: {t['SURFACE_ALT']};
        color: {t['TEXT_MUTED']};
        padding: 9px;
        border: none;
        border-right: 1px solid {t['BORDER']};
        font-weight: 600;
    }}
    QProgressBar {{
        min-height: 12px;
        background: {t['SURFACE_ALT']};
        border: 1px solid {t['BORDER']};
        border-radius: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {t['PRIMARY']}; border-radius: 5px; }}
    QCheckBox, QRadioButton {{ spacing: 8px; min-height: 28px; }}
    QGroupBox {{ margin-top: 12px; padding: 14px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QWidget#ScrollViewport, QWidget#ScrollBody {{ background: {t['BG']}; }}
    """


def build_application_font() -> QFont:
    """Return a Windows-first font stack with CJK and emoji fallbacks."""

    font = QFont()
    font.setFamilies(
        ["Microsoft YaHei UI", "Segoe UI", "Segoe UI Emoji", "sans-serif"]
    )
    font.setPointSize(10)
    return font

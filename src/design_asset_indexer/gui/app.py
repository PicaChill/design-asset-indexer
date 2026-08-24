"""Dependency-safe entry point for the optional desktop GUI."""

from __future__ import annotations

import sys
from typing import Sequence

from . import GUI_EXTRA_HINT


def create_public_window(*, auto_environment_check: bool = True):
    """Create the current public window without importing Qt at module import time."""

    from .premium_simple_window import PremiumSimpleWindow

    return PremiumSimpleWindow(auto_environment_check=auto_environment_check)


def main(argv: Sequence[str] | None = None) -> int:
    """Launch the GUI or print a concise optional-dependency hint."""

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "GUI 组件尚未安装。请安装 GUI 与 Photoshop 可选依赖：\n"
            f"  {GUI_EXTRA_HINT}",
            file=sys.stderr,
        )
        return 2

    from .theme import build_application_font, build_stylesheet

    arguments = list(argv) if argv is not None else sys.argv
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(arguments)
    application.setApplicationName("Design Asset Indexer")
    application.setOrganizationName("PicaChill")
    application.setStyle("Fusion")
    application.setFont(build_application_font())
    application.setStyleSheet(build_stylesheet())
    window = create_public_window()
    window.show()
    return application.exec()

"""Dependency-safe entry point for the optional desktop GUI."""

from __future__ import annotations

import sys
from typing import Sequence

from . import GUI_EXTRA_HINT


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

    from .main_window import MainWindow
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
    window = MainWindow()
    window.show()
    return application.exec()

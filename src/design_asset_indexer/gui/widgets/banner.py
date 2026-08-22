from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ..theme import TOKENS


class Banner(QFrame):
    """Wrapping message banner with success/warning/error styling."""

    def __init__(self, text: str = "", kind: str = "info", parent=None) -> None:
        super().__init__(parent)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.addWidget(self.label)
        self.set_kind(kind)
        self.setVisible(bool(text))

    def set_message(self, text: str, kind: str = "info") -> None:
        self.label.setText(text)
        self.set_kind(kind)
        self.setVisible(bool(text))

    def set_kind(self, kind: str) -> None:
        color = {
            "success": TOKENS["SUCCESS"],
            "warning": TOKENS["WARNING"],
            "error": TOKENS["ERROR"],
            "info": TOKENS["PRIMARY"],
        }.get(kind, TOKENS["PRIMARY"])
        self.setStyleSheet(
            f"QFrame {{ background: {TOKENS['SURFACE_ALT']}; "
            f"border: 1px solid {color}; border-radius: 8px; }}"
        )

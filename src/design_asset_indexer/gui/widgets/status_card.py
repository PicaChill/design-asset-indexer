from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from ..theme import TOKENS


class StatusCard(QFrame):
    def __init__(self, title: str, accent: str = "PRIMARY", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("Muted")
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {TOKENS[accent]};"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: int | str) -> None:
        self.value_label.setText(str(value))

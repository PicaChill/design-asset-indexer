from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QToolButton, QWidget


class PathPicker(QWidget):
    path_changed = Signal(str)

    def __init__(self, placeholder: str, dialog_title: str, parent=None) -> None:
        super().__init__(parent)
        self.dialog_title = dialog_title
        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)
        self.button = QToolButton()
        self.button.setText("选择")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.button)
        self.line_edit.textChanged.connect(self.path_changed)
        self.button.clicked.connect(self.choose_directory)

    @property
    def path(self) -> str:
        return self.line_edit.text().strip()

    def set_path(self, value: str) -> None:
        self.line_edit.setText(value)

    def choose_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            self.dialog_title,
            self.path or "",
        )
        if chosen:
            self.set_path(chosen)

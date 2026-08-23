"""Qt item models for typed workflow results."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Generic, Iterable, Sequence, TypeVar

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from ..workflow_models import ExecutionItemResult, InspectItem, PlanItem
from .theme import TOKENS


T = TypeVar("T")


class TypedTableModel(QAbstractTableModel, Generic[T]):
    headers: tuple[str, ...] = ()

    def __init__(self, items: Iterable[T] = (), parent=None) -> None:
        super().__init__(parent)
        self._items = tuple(items)

    @property
    def items(self) -> tuple[T, ...]:
        return self._items

    def set_items(self, items: Iterable[T]) -> None:
        self.beginResetModel()
        self._items = tuple(items)
        self.endResetModel()

    def item_at(self, row: int) -> T:
        return self._items[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(self.headers)
        ):
            return self.headers[section]
        return None


class InspectTableModel(TypedTableModel[InspectItem]):
    headers = ("PSD", "图层名", "图层路径", "当前文字", "状态", "选择")

    def __init__(self, items: Iterable[InspectItem] = (), parent=None) -> None:
        super().__init__(items, parent)
        self.selected_row = -1

    def set_items(self, items: Iterable[InspectItem]) -> None:
        self.selected_row = -1
        super().set_items(items)

    def set_selected_row(self, row: int) -> None:
        previous = self.selected_row
        self.selected_row = row
        for changed in (previous, row):
            if 0 <= changed < self.rowCount():
                self.dataChanged.emit(
                    self.index(changed, 5),
                    self.index(changed, 5),
                    [Qt.ItemDataRole.DisplayRole],
                )

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                PurePosixPath(item.relative_path).name,
                item.layer_name or "—",
                item.layer_path or "—",
                item.current_text or "—",
                item.error or ("已检查" if item.document_opened else "未打开"),
                "●" if index.row() == self.selected_row else "",
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.relative_path
        if role == Qt.ItemDataRole.ForegroundRole and item.error:
            return QColor(TOKENS["ERROR"])
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 5:
            return Qt.AlignmentFlag.AlignCenter
        return None


DECISION_LABELS = {
    "WOULD_REPLACE": "会修改",
    "SKIP_NO_MATCH": "没找到",
    "SKIP_AMBIGUOUS": "多个候选",
    "SKIP_EXISTS": "输出已存在",
    "ERROR": "错误",
}


class PlanTableModel(TypedTableModel[PlanItem]):
    headers = ("PSD", "预演结果", "匹配数", "输出位置", "错误")

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                PurePosixPath(item.relative_path).name,
                DECISION_LABELS.get(item.decision, item.decision),
                item.matched_layer_count,
                item.output_relative_path or "—",
                item.error_code or "—",
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.decision if index.column() == 1 else item.relative_path
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 2:
            return Qt.AlignmentFlag.AlignCenter
        return None


STATUS_LABELS = {
    "REPLACED": "已替换",
    "SKIPPED_NO_MATCH": "未匹配",
    "SKIPPED_AMBIGUOUS": "多候选",
    "SKIPPED_EXISTS": "已存在",
    "FAILED_OPEN": "打开失败",
    "FAILED_SAVE": "保存失败",
    "FAILED_REPLACE": "替换失败",
}


class ResultTableModel(TypedTableModel[ExecutionItemResult]):
    headers = ("PSD", "状态", "匹配数", "修改数", "输出", "错误")

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            values = (
                PurePosixPath(item.relative_path).name,
                STATUS_LABELS.get(item.status, item.status),
                item.matched_layer_count,
                item.changed_layer_count,
                item.output_relative_path or "—",
                item.error_code or "—",
            )
            return values[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 5 and item.error_message:
                return f"{item.error_code}: {item.error_message}"
            return item.relative_path
        if role == Qt.ItemDataRole.ForegroundRole and item.status.startswith("FAILED"):
            return QColor(TOKENS["ERROR"])
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (2, 3):
            return Qt.AlignmentFlag.AlignCenter
        return None


class InspectFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.search_text = ""
        self.mode = "全部"

    def set_search_text(self, text: str) -> None:
        self.search_text = text.casefold().strip()
        self.invalidateFilter()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if not isinstance(model, InspectTableModel):
            return True
        item = model.item_at(source_row)
        if self.mode == "有文字" and not item.current_text:
            return False
        if self.mode == "错误" and not item.error:
            return False
        if not self.search_text:
            return True
        haystack = "\n".join(
            (item.current_text, item.layer_name, item.layer_path)
        ).casefold()
        return self.search_text in haystack


class ResultFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode = "全部"

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if not isinstance(model, ResultTableModel):
            return True
        status = model.item_at(source_row).status
        if self.mode == "成功":
            return status == "REPLACED"
        if self.mode == "跳过":
            return status.startswith("SKIPPED")
        if self.mode == "失败":
            return status.startswith("FAILED")
        return True


def status_counts(items: Sequence[PlanItem | ExecutionItemResult], attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(getattr(item, attribute))
        counts[value] = counts.get(value, 0) + 1
    return counts

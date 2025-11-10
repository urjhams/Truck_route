"""
Reusable Qt table-model helpers for adapting SQLModel rows to the UI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from TruckRouteApp.ui.i18n import i18n, tr


class ColumnConfig:
    """Model column definition coupling header text with a value extractor."""

    def __init__(self, header: str, extractor: Callable, translate: bool = True):
        self.header = header
        self.extractor = extractor
        self.translate = translate

    def translated_header(self) -> str:
        if not self.translate:
            return self.header
        return tr(self.header)


class SQLModelTableModel(QAbstractTableModel):
    """
    Generic Qt table model that adapts SQLModel rows for presentation.
    Column descriptors supply both header labels and value extraction logic.
    """

    def __init__(self, columns: Sequence[ColumnConfig], parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: List = []
        i18n.language_changed.connect(self._on_language_changed)

    def set_rows(self, rows: Sequence) -> None:
        """Replace the backing data set with the provided rows."""
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._columns)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            row = self._rows[index.row()]
            col = self._columns[index.column()]
            value = col.extractor(row)
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%d %H:%M")
            return value
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section].translated_header()
        return section + 1

    def get_row(self, index: QModelIndex):
        if not index.isValid():
            return None
        return self._rows[index.row()]

    def _on_language_changed(self, _language: str) -> None:
        if self.columnCount() == 0:
            return
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)

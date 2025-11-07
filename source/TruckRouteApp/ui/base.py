"""
Building blocks for CRUD views shared across the desktop UI.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from TruckRouteApp.ui.table_models import SQLModelTableModel


class BaseCrudView(QWidget):
    """
    Shared UI scaffolding for CRUD list views with a table and common actions.
    Subclasses supply their own data model and handlers for the toolbar buttons.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.table = QTableView(self)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.model: SQLModelTableModel = None  # type: ignore
        self.main_layout.addWidget(self.table)

        self.button_bar = QHBoxLayout()
        self.main_layout.addLayout(self.button_bar)

        self.add_button = QPushButton("Add", self)
        self.edit_button = QPushButton("Edit", self)
        self.delete_button = QPushButton("Delete", self)
        self.refresh_button = QPushButton("Refresh", self)
        for widget in (self.add_button, self.edit_button, self.delete_button, self.refresh_button):
            self.button_bar.addWidget(widget)

    def selected_index(self) -> Optional[QModelIndex]:
        """Return the currently selected row index or None when nothing is selected."""
        selection = self.table.selectionModel()
        if not selection:
            return None
        indexes = selection.selectedRows()
        if not indexes:
            return None
        return indexes[0]

    def set_model(self, model: SQLModelTableModel) -> None:
        self.model = model
        self.table.setModel(model)
        self.table.resizeColumnsToContents()

    def _on_double_clicked(self, index: QModelIndex) -> None:
        """Invoke the subclass `edit` handler when the user double-clicks a row."""
        if not index.isValid():
            return
        if hasattr(self, "edit"):
            try:
                getattr(self, "edit")()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Unable to open editor: {exc}")


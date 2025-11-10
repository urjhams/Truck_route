"""
Application main window wiring together navigation and CRUD views.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.ui.i18n import LANGUAGE_OPTIONS, i18n, tr
from TruckRouteApp.ui.views import CustomerView, ItemView, OrderView, WarehouseView


class MainWindow(QMainWindow):
    """Top-level window containing navigation and the individual CRUD views."""

    def __init__(self, db_service: DatabaseService):
        super().__init__()
        self.db_service = db_service
        self.setWindowTitle(tr("Truck Route Planner"))
        self.resize(1280, 800)

        splitter = QSplitter(self)
        splitter.setOrientation(Qt.Orientation.Horizontal)

        self.nav_keys = ["Warehouses", "Customers", "Items", "Orders"]
        self.nav_list = QListWidget(self)
        for key in self.nav_keys:
            item = QListWidgetItem(tr(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav_list.addItem(item)

        sidebar = QWidget(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)
        language_row = QHBoxLayout()
        self.language_label = QLabel(sidebar)
        self.language_combo = QComboBox(sidebar)
        for code, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(tr(label), code)
        current_index = next(
            (idx for idx, (code, _) in enumerate(LANGUAGE_OPTIONS) if code == i18n.language),
            0,
        )
        self.language_combo.setCurrentIndex(current_index)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo)
        sidebar_layout.addLayout(language_row)
        sidebar_layout.addWidget(self.nav_list)

        self.export_db_button = QPushButton(sidebar)
        self.import_db_button = QPushButton(sidebar)
        sidebar_layout.addWidget(self.export_db_button)
        sidebar_layout.addWidget(self.import_db_button)
        sidebar_layout.addStretch()

        splitter.addWidget(sidebar)

        self.stack = QWidget(self)
        self.stack_layout = QVBoxLayout(self.stack)

        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)

        self.views = {
            "Warehouses": WarehouseView(self.db_service, self),
            "Customers": CustomerView(self.db_service, self),
            "Items": ItemView(self.db_service, self),
            "Orders": OrderView(self.db_service, self),
        }
        for idx, view in enumerate(self.views.values()):
            self.stack_layout.addWidget(view)
            view.setVisible(idx == 0)

        self.nav_list.currentRowChanged.connect(self.on_nav_changed)
        self.nav_list.setCurrentRow(0)
        self.export_db_button.clicked.connect(self.export_database)
        self.import_db_button.clicked.connect(self.import_database)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()

    def on_nav_changed(self, row: int):
        """Swap the visible view when the user selects a different navigation item."""
        item = self.nav_list.item(row)
        if not item:
            return
        view_key = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not view_key:
            return
        for name, view in self.views.items():
            view.setVisible(name == view_key)

    def export_database(self):
        """Prompt for a destination and copy the SQLite file there."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export database"),
            "",
            tr("SQLite database (*.db);;All files (*)"),
        )
        if not path:
            return
        try:
            destination = self.db_service.export_database(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Export failed"), str(exc))
            return
        QMessageBox.information(
            self,
            tr("Export complete"),
            tr("Database exported to:\n{destination}").format(destination=destination),
        )

    def import_database(self):
        """Replace the current SQLite DB with the selected file after confirmation."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Import database"),
            "",
            tr("SQLite database (*.db);;All files (*)"),
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self,
            tr("Import database"),
            tr("Importing will overwrite the current data. Continue?"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            destination = self.db_service.import_database(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Import failed"), str(exc))
            return
        self.refresh_all_views()
        QMessageBox.information(
            self,
            tr("Import complete"),
            tr("Database replaced with:\n{destination}").format(destination=destination),
        )

    def refresh_all_views(self) -> None:
        for view in self.views.values():
            refresh = getattr(view, "refresh", None)
            if callable(refresh):
                refresh()

    def _apply_translations(self) -> None:
        self.setWindowTitle(tr("Truck Route Planner"))
        self.language_label.setText(tr("Language"))
        for index in range(self.nav_list.count()):
            item = self.nav_list.item(index)
            key = item.data(Qt.ItemDataRole.UserRole)
            if key:
                item.setText(tr(key))
        self.export_db_button.setText(tr("Export database"))
        self.import_db_button.setText(tr("Import database"))
        # Update combo display names to ensure current text is localized.
        for index, (code, label) in enumerate(LANGUAGE_OPTIONS):
            self.language_combo.setItemText(index, tr(label))

    def _on_language_changed(self, index: int) -> None:
        code = self.language_combo.itemData(index)
        if not code:
            return
        i18n.set_language(code)

"""
Application main window wiring together navigation and CRUD views.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.ui.views import CustomerView, ItemView, OrderView, WarehouseView


class MainWindow(QMainWindow):
    """Top-level window containing navigation and the individual CRUD views."""

    def __init__(self, db_service: DatabaseService):
        super().__init__()
        self.db_service = db_service
        self.setWindowTitle("Truck Route Planner")
        self.resize(1280, 800)

        splitter = QSplitter(self)
        splitter.setOrientation(Qt.Orientation.Horizontal)

        self.nav_list = QListWidget(self)
        self.nav_list.addItem("Warehouses")
        self.nav_list.addItem("Customers")
        self.nav_list.addItem("Items")
        self.nav_list.addItem("Orders")

        sidebar = QWidget(self)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(12)
        sidebar_layout.addWidget(self.nav_list)

        self.export_db_button = QPushButton("Export database", sidebar)
        self.import_db_button = QPushButton("Import database", sidebar)
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

    def on_nav_changed(self, row: int):
        """Swap the visible view when the user selects a different navigation item."""
        item = self.nav_list.item(row)
        if not item:
            return
        view_name = item.text()
        for name, view in self.views.items():
            view.setVisible(name == view_name)

    def export_database(self):
        """Prompt for a destination and copy the SQLite file there."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export database",
            "",
            "SQLite database (*.db);;All files (*)",
        )
        if not path:
            return
        try:
            destination = self.db_service.export_database(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Database exported to:\n{destination}")

    def import_database(self):
        """Replace the current SQLite DB with the selected file after confirmation."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import database",
            "",
            "SQLite database (*.db);;All files (*)",
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self,
            "Import database",
            "Importing will overwrite the current data. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            destination = self.db_service.import_database(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.refresh_all_views()
        QMessageBox.information(self, "Import complete", f"Database replaced with:\n{destination}")

    def refresh_all_views(self) -> None:
        for view in self.views.values():
            refresh = getattr(view, "refresh", None)
            if callable(refresh):
                refresh()

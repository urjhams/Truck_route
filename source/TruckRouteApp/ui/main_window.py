"""
Application main window wiring together navigation and CRUD views.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QMainWindow, QSplitter, QVBoxLayout, QWidget

from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.ui.views import CustomerView, ItemView, OrderView, WarehouseView


class MainWindow(QMainWindow):
    """Top-level window containing navigation and the individual CRUD views."""

    def __init__(self, db_service: DatabaseService):
        super().__init__()
        self.db_service = db_service
        self.setWindowTitle("Truck Route Planner")
        self.resize(1100, 700)

        splitter = QSplitter(self)
        splitter.setOrientation(Qt.Orientation.Horizontal)

        self.nav_list = QListWidget(self)
        self.nav_list.addItem("Warehouses")
        self.nav_list.addItem("Customers")
        self.nav_list.addItem("Items")
        self.nav_list.addItem("Orders")
        splitter.addWidget(self.nav_list)

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

    def on_nav_changed(self, row: int):
        """Swap the visible view when the user selects a different navigation item."""
        item = self.nav_list.item(row)
        if not item:
            return
        view_name = item.text()
        for name, view in self.views.items():
            view.setVisible(name == view_name)


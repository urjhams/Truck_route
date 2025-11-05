"""
GUI entry point for the Truck Route desktop application.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from TruckRouteApp.db import init_db
from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.logic.export_excel import DEFAULT_TEMPLATE, RouteExcelRow, export_route_to_excel
from TruckRouteApp.logic.routing_local import Stop, RouteResult, haversine_meters, optimise_route
from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse


class ColumnConfig:
    def __init__(self, header: str, extractor: Callable):
        self.header = header
        self.extractor = extractor


class SQLModelTableModel(QAbstractTableModel):
    def __init__(self, columns: Sequence[ColumnConfig], parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: List = []

    def set_rows(self, rows: Sequence) -> None:
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
            return self._columns[section].header
        return section + 1

    def get_row(self, index: QModelIndex):
        if not index.isValid():
            return None
        return self._rows[index.row()]


class BaseCrudView(QWidget):
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
        if not index.isValid():
            return
        if hasattr(self, "edit"):
            try:
                getattr(self, "edit")()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Unable to open editor: {exc}")


class WarehouseDialog(QDialog):
    def __init__(self, warehouse: Optional[Warehouse] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Warehouse")
        self.warehouse = warehouse or Warehouse(name="", lat=0.0, lng=0.0)

        form = QFormLayout(self)
        self.name_edit = QLineEdit(self.warehouse.name, self)
        self.address_edit = QLineEdit(self.warehouse.address or "", self)
        self.lat_edit = QLineEdit(
            "" if self.warehouse.lat is None else str(self.warehouse.lat),
            self,
        )
        self.lng_edit = QLineEdit(
            "" if self.warehouse.lng is None else str(self.warehouse.lng),
            self,
        )
        form.addRow("Name", self.name_edit)
        form.addRow("Address", self.address_edit)
        form.addRow("Latitude", self.lat_edit)
        form.addRow("Longitude", self.lng_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> Optional[Warehouse]:
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None
            try:
                lat = float(self.lat_edit.text())
                lng = float(self.lng_edit.text())
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Latitude and longitude must be numeric.")
                continue

            self.warehouse.name = self.name_edit.text()
            self.warehouse.address = self.address_edit.text()
            self.warehouse.lat = lat
            self.warehouse.lng = lng
            return self.warehouse


class CustomerDialog(QDialog):
    def __init__(self, customer: Optional[Customer] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customer")
        self.customer = customer or Customer(name="", lat=0.0, lng=0.0)

        form = QFormLayout(self)
        self.name_edit = QLineEdit(self.customer.name, self)
        self.address_edit = QLineEdit(self.customer.address or "", self)
        self.lat_edit = QLineEdit(
            "" if self.customer.lat is None else str(self.customer.lat),
            self,
        )
        self.lng_edit = QLineEdit(
            "" if self.customer.lng is None else str(self.customer.lng),
            self,
        )
        form.addRow("Name", self.name_edit)
        form.addRow("Address", self.address_edit)
        form.addRow("Latitude", self.lat_edit)
        form.addRow("Longitude", self.lng_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> Optional[Customer]:
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None
            try:
                lat = float(self.lat_edit.text())
                lng = float(self.lng_edit.text())
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Latitude and longitude must be numeric.")
                continue

            self.customer.name = self.name_edit.text()
            self.customer.address = self.address_edit.text()
            self.customer.lat = lat
            self.customer.lng = lng
            return self.customer


class ItemDialog(QDialog):
    def __init__(self, item: Optional[Item] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Item")
        self.item = item or Item(name="")

        form = QFormLayout(self)
        self.name_edit = QLineEdit(self.item.name, self)
        self.weight_edit = QLineEdit(
            "" if self.item.weight_per_ctn is None else str(self.item.weight_per_ctn),
            self,
        )
        self.ctn_edit = QLineEdit(
            "" if self.item.ctn_per_pallet is None else str(self.item.ctn_per_pallet),
            self,
        )
        form.addRow("Name", self.name_edit)
        form.addRow("Weight per ctn", self.weight_edit)
        form.addRow("Ctn per pallet", self.ctn_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> Optional[Item]:
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None

            try:
                weight = float(self.weight_edit.text()) if self.weight_edit.text() else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Weight must be numeric.")
                continue

            try:
                ctn = int(self.ctn_edit.text()) if self.ctn_edit.text() else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Cartons per pallet must be integer.")
                continue

            self.item.name = self.name_edit.text()
            self.item.weight_per_ctn = weight
            self.item.ctn_per_pallet = ctn
            return self.item


class WarehouseView(BaseCrudView):
    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        columns = [
            ColumnConfig("Name", lambda w: w.name),
            ColumnConfig("Address", lambda w: w.address or ""),
            ColumnConfig("Latitude", lambda w: w.lat),
            ColumnConfig("Longitude", lambda w: w.lng),
        ]
        model = SQLModelTableModel(columns, self)
        self.set_model(model)

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        
        self.refresh()

    def refresh(self):
        self.model.set_rows(self.db.list_warehouses())
        self.table.resizeColumnsToContents()

    def add(self):
        dialog = WarehouseDialog(parent=self)
        data = dialog.get_data()
        if data:
            self.db.save_warehouse(data)
            self.refresh()

    def edit(self):
        index = self.selected_index()
        if not index:
            return
        warehouse: Optional[Warehouse] = self.model.get_row(index)
        if not warehouse:
            return
        dialog = WarehouseDialog(warehouse=warehouse, parent=self)
        data = dialog.get_data()
        if data:
            self.db.save_warehouse(data)
            self.refresh()

    def delete(self):
        index = self.selected_index()
        if not index or not self.model:
            return
        warehouse = self.model.get_row(index)
        if not warehouse:
            return
        confirm = QMessageBox.question(
            self,
            "Delete warehouse",
            f"Delete warehouse '{warehouse.name}'?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_warehouse(warehouse.id)
            self.refresh()


class CustomerView(BaseCrudView):
    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        columns = [
            ColumnConfig("Name", lambda c: c.name),
            ColumnConfig("Address", lambda c: c.address or ""),
            ColumnConfig("Latitude", lambda c: c.lat),
            ColumnConfig("Longitude", lambda c: c.lng),
        ]
        self.model = SQLModelTableModel(columns, self)
        self.set_model(self.model)
        self.refresh()

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)

    def refresh(self):
        self.model.set_rows(self.db.list_customers())
        self.table.resizeColumnsToContents()

    def add(self):
        dialog = CustomerDialog(parent=self)
        data = dialog.get_data()
        if data:
            self.db.save_customer(data)
            self.refresh()

    def edit(self):
        index = self.selected_index()
        if not index:
            return
        customer: Optional[Customer] = self.model.get_row(index)
        if not customer:
            return
        dialog = CustomerDialog(customer=customer, parent=self)
        data = dialog.get_data()
        if data:
            self.db.save_customer(data)
            self.refresh()

    def delete(self):
        index = self.selected_index()
        if not index:
            return
        customer: Optional[Customer] = self.model.get_row(index)
        if not customer:
            return
        confirm = QMessageBox.question(
            self,
            "Delete customer",
            f"Delete customer '{customer.name}'?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_customer(customer.id)
            self.refresh()


class ItemView(BaseCrudView):
    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        columns = [
            ColumnConfig("Name", lambda item: item.name),
            ColumnConfig("Weight/ctn", lambda item: item.weight_per_ctn or ""),
            ColumnConfig("Cartons/pallet", lambda item: item.ctn_per_pallet or ""),
        ]
        self.model = SQLModelTableModel(columns, self)
        self.set_model(self.model)
        self.refresh()

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)

    def refresh(self):
        self.model.set_rows(self.db.list_items())
        self.table.resizeColumnsToContents()

    def add(self):
        dialog = ItemDialog(parent=self)
        data = dialog.get_data()
        if data:
            self.db.save_item(data)
            self.refresh()

    def edit(self):
        index = self.selected_index()
        if not index:
            return
        item: Optional[Item] = self.model.get_row(index)
        if not item:
            return
        dialog = ItemDialog(item=item, parent=self)
        data = dialog.get_data()
        if data:
            self.db.save_item(data)
            self.refresh()

    def delete(self):
        index = self.selected_index()
        if not index:
            return
        item: Optional[Item] = self.model.get_row(index)
        if not item:
            return
        confirm = QMessageBox.question(
            self,
            "Delete item",
            f"Delete item '{item.name}'?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_item(item.id)
            self.refresh()


@dataclass
class OrderLineEntry:
    customer: Customer
    item: Item
    quantity: int


class RouteCalculationWorker(QObject):
    finished = Signal(object, object)  # Tuple[Optional[RouteResult], Optional[BaseException]]

    def __init__(self, stops: Sequence[Stop], return_to_depot: bool = True, parent=None):
        super().__init__(parent)
        self._stops = list(stops)
        self._return_to_depot = return_to_depot

    def run(self) -> None:
        try:
            result = optimise_route(self._stops, return_to_depot=self._return_to_depot)
        except Exception as exc:  # propagate error to GUI thread
            self.finished.emit(None, exc)
            return
        self.finished.emit(result, None)


class OrderLineDialog(QDialog):
    def __init__(self, customers: Sequence[Customer], items: Sequence[Item], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Line")
        self.customers = list(customers)
        self.items = list(items)
        self.selected: Optional[OrderLineEntry] = None

        form = QFormLayout(self)
        self.customer_combo = QComboBox(self)
        for customer in self.customers:
            self.customer_combo.addItem(customer.name, customer)

        self.item_combo = QComboBox(self)
        for item in self.items:
            self.item_combo.addItem(item.name, item)

        self.qty_spin = QSpinBox(self)
        self.qty_spin.setRange(1, 100000)
        self.qty_spin.setValue(1)

        form.addRow("Customer", self.customer_combo)
        form.addRow("Item", self.item_combo)
        form.addRow("Quantity", self.qty_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_line(self) -> Optional[OrderLineEntry]:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        customer = self.customer_combo.currentData()
        item = self.item_combo.currentData()
        quantity = int(self.qty_spin.value())
        return OrderLineEntry(customer=customer, item=item, quantity=quantity)


class OrderDialog(QDialog):
    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Create Order")
        self.resize(720, 500)

        self.warehouses = self.db.list_warehouses()
        self.customers = self.db.list_customers()
        self.items = self.db.list_items()

        if not self.warehouses:
            QMessageBox.warning(self, "Missing data", "Please create at least one warehouse first.")
        if not self.customers:
            QMessageBox.warning(self, "Missing data", "Please create at least one customer first.")
        if not self.items:
            QMessageBox.warning(self, "Missing data", "Please create at least one item first.")

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        self.warehouse_combo = QComboBox(self)
        for warehouse in self.warehouses:
            self.warehouse_combo.addItem(warehouse.name, warehouse)
        form_layout.addRow("Warehouse", self.warehouse_combo)

        self.line_table = QTableWidget(0, 4, self)
        self.line_table.setHorizontalHeaderLabels(["Customer", "Item", "Quantity", ""])
        self.line_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QLabel("Order Lines"))
        layout.addWidget(self.line_table)

        line_buttons = QHBoxLayout()
        layout.addLayout(line_buttons)
        self.add_line_button = QPushButton("Add line", self)
        self.remove_line_button = QPushButton("Remove selected", self)
        line_buttons.addWidget(self.add_line_button)
        line_buttons.addWidget(self.remove_line_button)

        layout.addWidget(QLabel("Route preview (drag to reorder)"))
        self.route_list = QListWidget(self)
        self.route_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(self.route_list)

        self.route_status_label = QLabel("", self)
        layout.addWidget(self.route_status_label)

        route_buttons = QHBoxLayout()
        layout.addLayout(route_buttons)
        self.estimate_button = QPushButton("Estimate route", self)
        self.export_button = QPushButton("Export to Excel", self)
        self.export_button.setEnabled(False)
        route_buttons.addWidget(self.estimate_button)
        route_buttons.addWidget(self.export_button)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.add_line_button.clicked.connect(self.add_line)
        self.remove_line_button.clicked.connect(self.remove_line)
        self.estimate_button.clicked.connect(self.estimate_route)
        self.export_button.clicked.connect(self.export_route)

        self.lines: List[OrderLineEntry] = []
        self.route_order: List[int] = []  # customer IDs in the order list
        self.current_stops: List[Stop] = []
        self.stop_index_to_customer: dict[int, Customer] = {}
        self.route_thread: Optional[QThread] = None
        self.route_worker: Optional[RouteCalculationWorker] = None

    def add_line(self):
        dialog = OrderLineDialog(self.customers, self.items, self)
        entry = dialog.get_line()
        if not entry:
            return

        self.lines.append(entry)
        row = self.line_table.rowCount()
        self.line_table.insertRow(row)
        self.line_table.setItem(row, 0, QTableWidgetItem(entry.customer.name))
        self.line_table.setItem(row, 1, QTableWidgetItem(entry.item.name))
        self.line_table.setItem(row, 2, QTableWidgetItem(str(entry.quantity)))
        remove_btn = QPushButton("Remove", self.line_table)
        remove_btn.clicked.connect(lambda _, r=row: self._remove_line_at(r))
        self.line_table.setCellWidget(row, 3, remove_btn)

    def _remove_line_at(self, row: int):
        if 0 <= row < len(self.lines):
            self.lines.pop(row)
            self.line_table.removeRow(row)
        self.route_list.clear()
        self.export_button.setEnabled(False)
        self.route_status_label.clear()

    def remove_line(self):
        row = self.line_table.currentRow()
        if row >= 0:
            self._remove_line_at(row)

    def _build_stops(self) -> Optional[List[Stop]]:
        if not self.lines:
            QMessageBox.warning(self, "Missing lines", "Please add at least one order line.")
            return None
        warehouse: Warehouse = self.warehouse_combo.currentData()
        stops = [Stop(name=warehouse.name, lat=warehouse.lat, lng=warehouse.lng)]
        self.stop_index_to_customer = {}
        seen_ids = set()
        for entry in self.lines:
            if entry.customer.id in seen_ids:
                continue
            seen_ids.add(entry.customer.id)
            stops.append(Stop(name=entry.customer.name, lat=entry.customer.lat, lng=entry.customer.lng))
            self.stop_index_to_customer[len(stops) - 1] = entry.customer
        return stops

    def estimate_route(self):
        if self.route_thread and self.route_thread.isRunning():
            QMessageBox.information(self, "Route calculation", "A route calculation is already in progress.")
            return
        try:
            stops = self._build_stops()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        if not stops:
            return

        self.current_stops = stops
        self.route_list.clear()
        self.route_order = []
        self.export_button.setEnabled(False)
        self.estimate_button.setEnabled(False)
        self.route_status_label.setText("Calculating route...")

        worker = RouteCalculationWorker(stops, return_to_depot=True)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_route_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_route_thread_finished)
        self.route_worker = worker
        self.route_thread = thread
        thread.start()

    def _on_route_finished(self, result: Optional[RouteResult], error: Optional[BaseException]) -> None:
        self.route_worker = None
        self.estimate_button.setEnabled(True)
        if error or result is None:
            message = str(error) if error else "Unable to compute route."
            self.route_status_label.setText("Route calculation failed.")
            QMessageBox.critical(self, "Routing error", message)
            return

        self._populate_route_list(result)
        km = result.total_distance_m / 1000 if result.total_distance_m else 0
        self.route_status_label.setText(f"Route ready — total distance ≈ {km:.2f} km")
        self.export_button.setEnabled(True)

    def _populate_route_list(self, result: RouteResult) -> None:
        stops = self.current_stops
        if not stops:
            return
        self.route_list.clear()
        self.route_order = []

        for position, idx in enumerate(result.route_nodes):
            if position != 0 and idx == 0:
                continue  # skip duplicate depot at the end
            stop = stops[idx]
            if idx == 0:
                item = QListWidgetItem(f"{stop.name} (Depot)")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            else:
                item = QListWidgetItem(stop.name)
                item.setData(Qt.ItemDataRole.UserRole, idx)
                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsDragEnabled
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                )
                self.route_order.append(idx)
            self.route_list.addItem(item)

    def _on_route_thread_finished(self) -> None:
        self.route_thread = None
        if self.route_status_label.text() == "Calculating route...":
            self.route_status_label.clear()

    def export_route(self):
        if self.route_list.count() <= 1:
            QMessageBox.warning(self, "Route missing", "Please estimate the route first.")
            return
        warehouse: Warehouse = self.warehouse_combo.currentData()
        stops = self.current_stops or self._build_stops()
        if not stops:
            return

        ordered_customer_indices = []
        for row in range(self.route_list.count()):
            item = self.route_list.item(row)
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx and idx != 0:
                ordered_customer_indices.append(idx)

        ordered_indices = [0] + ordered_customer_indices
        rows: List[RouteExcelRow] = []
        lines_by_customer: dict[int, List[OrderLineEntry]] = {}
        for entry in self.lines:
            id = entry.customer.id
            if id:
                lines_by_customer.setdefault(id, []).append(entry)
        for position, stop_idx in enumerate(ordered_indices):
            stop = stops[stop_idx]
            next_idx = ordered_indices[(position + 1) % len(ordered_indices)]
            next_stop = stops[next_idx]
            distance = haversine_meters(stop.lat, stop.lng, next_stop.lat, next_stop.lng)
            address = ""
            customer = self.stop_index_to_customer.get(stop_idx) if stop_idx != 0 else None
            if stop_idx == 0:
                address = warehouse.address or ""
            elif customer:
                address = customer.address or ""
            rows.append(
                RouteExcelRow(
                    order=position,
                    stop_name=stop.name,
                    address=address,
                    lat=stop.lat,
                    lng=stop.lng,
                    distance_to_next_m=distance,
                    items_summary="; ".join(
                        f"{line.item.name} x{line.quantity}"
                        for line in lines_by_customer.get(customer.id, [])
                    )
                    if stop_idx != 0 and customer and customer.id is not None
                    else "",
                )
            )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export route",
            str(Path.home() / f"{warehouse.name}_route.xlsx"),
            "Excel files (*.xlsx)",
        )
        if not path:
            return

        metadata = {
            "Warehouse": warehouse.name,
            "Generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Stops": str(len(rows) - 1),
        }
        try:
            export_route_to_excel(Path(path), rows, metadata=metadata, template_path=DEFAULT_TEMPLATE)
        except Exception as exc:
            QMessageBox.critical(self, "Export error", str(exc))
            return

        QMessageBox.information(self, "Export complete", f"Excel file saved to {path}")

    def accept(self):
        if not self.lines:
            QMessageBox.warning(self, "Missing lines", "Add at least one order line.")
            return
        warehouse: Optional[Warehouse] = self.warehouse_combo.currentData()
        if not warehouse:
            QMessageBox.warning(self, "Missing warehouse", "Select a warehouse.")
            return
        super().accept()

    def get_payload(self) -> Optional[tuple[Order, List[OrderLine]]]:
        if self.exec() != QDialog.DialogCode.Accepted:
            return None

        warehouse: Warehouse = self.warehouse_combo.currentData()
        assert warehouse.id is not None
        order = Order(warehouse_id=warehouse.id)
        order_lines: List[OrderLine] = []
        for entry in self.lines:
            assert entry.customer.id is not None
            assert entry.item.id is not None
            order_lines.append(
                OrderLine(
                    order_id=0,
                    customer_id=entry.customer.id,
                    item_id=entry.item.id,
                    qty=entry.quantity,
                )
            )
        return order, order_lines


class OrderView(BaseCrudView):
    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        columns = [
            ColumnConfig("ID", lambda order: order.id),
            ColumnConfig("Warehouse", self._warehouse_name),
            ColumnConfig("Created", lambda order: order.created_at),
        ]
        self.model = SQLModelTableModel(columns, self)
        self.set_model(self.model)
        self.refresh()

        self.add_button.setText("Create order")
        self.edit_button.setVisible(False)

        self.add_button.clicked.connect(self.create_order)
        self.delete_button.clicked.connect(self.delete_order)
        self.refresh_button.clicked.connect(self.refresh)

    def _warehouse_name(self, order: Order):
        warehouse = self.db.get_warehouse(order.warehouse_id)
        return warehouse.name if warehouse else "Unknown"

    def refresh(self):
        self.model.set_rows(self.db.list_orders())
        self.table.resizeColumnsToContents()

    def create_order(self):
        dialog = OrderDialog(self.db, self)
        payload = dialog.get_payload()
        if not payload:
            return
        order, lines = payload
        self.db.create_order_with_lines(order, lines)
        self.refresh()

    def delete_order(self):
        index = self.selected_index()
        if not index:
            return
        order = self.model.get_row(index)
        if not order:
            return
        confirm = QMessageBox.question(
            self,
            "Delete order",
            f"Delete order #{order.id}?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_order(order.id)
            self.refresh()


class MainWindow(QMainWindow):
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
        item = self.nav_list.item(row)
        if not item:
            return
        view_name = item.text()
        for name, view in self.views.items():
            view.setVisible(name == view_name)


def main():
    init_db()
    db_service = DatabaseService()
    app = QApplication(sys.argv)
    window = MainWindow(db_service)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

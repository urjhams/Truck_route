"""
Dialogs and workers related to order creation, editing, and routing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, cast

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
)

from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.logic.export_excel import (
    DEFAULT_TEMPLATE,
    RouteExcelItem,
    RouteExcelRow,
    export_route_to_excel,
)
from TruckRouteApp.logic.routing_local import RouteResult, Stop, optimise_route
from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse


_ACTIVE_ROUTE_THREADS: List[QThread] = []


def _register_route_thread(thread: QThread) -> None:
    """Keep QThread instances alive until they finish, even if dialogs close."""
    _ACTIVE_ROUTE_THREADS.append(thread)

    def _cleanup() -> None:
        try:
            _ACTIVE_ROUTE_THREADS.remove(thread)
        except ValueError:
            pass
        try:
            thread.finished.disconnect(_cleanup)
        except RuntimeError:
            pass

    thread.finished.connect(_cleanup)


@dataclass
class OrderLineEntry:
    """In-memory representation of a line awaiting persistence on the order."""

    customer: Customer
    item: Item
    pallets: float
    ktn_per_pal: Optional[float] = None


class RouteCalculationWorker(QObject):
    """
    Worker object that performs route optimisation on a background thread.
    Emits a `(result, error)` tuple when finished so the UI can react safely.
    """

    finished = Signal(object, object)  # Tuple[Optional[RouteResult], Optional[BaseException]]

    def __init__(self, stops: Sequence[Stop], return_to_depot: bool = True, parent=None):
        super().__init__(parent)
        self._stops = list(stops)
        self._return_to_depot = return_to_depot

    def run(self) -> None:
        """Compute the optimal route and emit the outcome back to the main thread."""
        try:
            result = optimise_route(self._stops, return_to_depot=self._return_to_depot)
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(None, exc)
            return
        self.finished.emit(result, None)


class OrderLineDialog(QDialog):
    """Collect one or more order lines for a single customer in one shot."""

    def __init__(self, customers: Sequence[Customer], items: Sequence[Item], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Line")
        self.setMinimumWidth(560)
        self.customers = list(customers)
        self.items = list(items)
        self.selected_lines: List[OrderLineEntry] = []
        self._item_rows: List[dict[str, QWidget]] = []

        layout = QVBoxLayout(self)

        form = QFormLayout()
        layout.addLayout(form)
        self.customer_combo = QComboBox(self)
        for customer in self.customers:
            self.customer_combo.addItem(customer.name, customer)
        self.customer_combo.setMinimumWidth(260)
        form.addRow("Customer", self.customer_combo)

        layout.addWidget(QLabel("Products"))
        header_layout = QHBoxLayout()
        for title, stretch in (("Product", 3), ("Pallets", 1), ("Karton/Pal", 1)):
            label = QLabel(title, self)
            label.setStyleSheet("font-weight: 600;")
            if title == "Karton/Pal":
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(label, stretch)
        layout.addLayout(header_layout)

        self.items_layout = QVBoxLayout()
        layout.addLayout(self.items_layout)

        controls = QHBoxLayout()
        controls.addStretch()
        self.add_item_button = QPushButton("+", self)
        self.add_item_button.setFixedWidth(32)
        self.add_item_button.clicked.connect(self._add_item_row)
        self.remove_item_button = QPushButton("-", self)
        self.remove_item_button.setFixedWidth(32)
        self.remove_item_button.clicked.connect(self._remove_item_row)
        controls.addWidget(self.add_item_button)
        controls.addWidget(self.remove_item_button)
        layout.addLayout(controls)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.button_box.accepted.connect(self._handle_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self._add_item_row()
        self._update_remove_button_state()

    def _add_item_row(self) -> None:
        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        item_combo = QComboBox(row_widget)
        for item in self.items:
            item_combo.addItem(item.name, item)
        item_combo.setMinimumWidth(220)

        pallets_input = QLineEdit(row_widget)
        pallets_input.setPlaceholderText("Number of pallets")
        pallets_input.setMinimumWidth(120)
        validator = QDoubleValidator(0.0, 999999.0, 3, pallets_input)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        pallets_input.setValidator(validator)

        karton_input = QLineEdit(row_widget)
        karton_input.setPlaceholderText("Karton per pallet")
        karton_input.setMinimumWidth(120)
        karton_validator = QDoubleValidator(0.0, 999999.0, 3, karton_input)
        karton_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        karton_input.setValidator(karton_validator)

        row_layout.addWidget(item_combo, 3)
        row_layout.addWidget(pallets_input, 1)
        row_layout.addWidget(karton_input, 1)
        self.items_layout.addWidget(row_widget)

        row = {
            "widget": row_widget,
            "item_combo": item_combo,
            "pallets_input": pallets_input,
            "karton_input": karton_input,
        }
        self._item_rows.append(row)
        self._update_remove_button_state()

    def _remove_item_row(self) -> None:
        if len(self._item_rows) <= 1:
            return
        row = self._item_rows.pop()
        row_widget = row["widget"]
        row_widget.setParent(None)
        row_widget.deleteLater()
        self._update_remove_button_state()

    def _update_remove_button_state(self) -> None:
        self.remove_item_button.setEnabled(len(self._item_rows) > 1)

    def _handle_accept(self) -> None:
        customer: Customer = self.customer_combo.currentData()
        lines: List[OrderLineEntry] = []
        errors: List[str] = []
        for idx, row in enumerate(self._item_rows, start=1):
            # row["item_combo"] is stored as a QWidget in the dict; cast it to QComboBox
            # and cast the returned currentData() to Item so the type checker understands.
            item: Item = cast(Item, cast(QComboBox, row["item_combo"]).currentData())
            pallets_text = cast(QLineEdit, row["pallets_input"]).text().strip()
            karton_text = cast(QLineEdit, row["karton_input"]).text().strip()
            if not pallets_text:
                errors.append(f"Row {idx}: pallet count is required.")
                continue
            pallets = float(pallets_text)
            if pallets <= 0:
                errors.append(f"Row {idx}: pallet count must be greater than zero.")
                continue
            karton = float(karton_text) if karton_text else None
            lines.append(
                OrderLineEntry(
                    customer=customer,
                    item=item,
                    pallets=pallets,
                    ktn_per_pal=karton,
                )
            )
        if errors:
            QMessageBox.warning(self, "Validation error", "\n".join(errors))
            return
        if not lines:
            QMessageBox.warning(self, "Validation error", "Add at least one product.")
            return

        self.selected_lines = lines
        self.accept()


class OrderDialog(QDialog):
    """Collect order metadata, order lines, and optional routing/export steps."""

    def __init__(self, db: DatabaseService, parent=None, order: Optional[Order] = None):
        super().__init__(parent)
        self.db = db
        self.order = order
        self.setWindowTitle("Order")
        self.resize(900, 640)

        self.customers_all = self.db.list_customers()
        self.customers_with_coordinates = [c for c in self.customers_all if c.lat is not None and c.lng is not None]
        self.items = self.db.list_items()
        self.warehouses = self.db.list_warehouses()

        main_layout = QVBoxLayout(self)

        form = QFormLayout()
        self.warehouse_combo = QComboBox(self)
        for warehouse in self.warehouses:
            self.warehouse_combo.addItem(warehouse.name, warehouse)
        form.addRow("Warehouse", self.warehouse_combo)
        main_layout.addLayout(form)

        line_controls = QHBoxLayout()
        self.add_line_button = QPushButton("Add line", self)
        self.remove_line_button = QPushButton("Remove line", self)
        line_controls.addWidget(self.add_line_button)
        line_controls.addWidget(self.remove_line_button)
        line_controls.addStretch()
        main_layout.addLayout(line_controls)

        self.line_table = QTableWidget(self)
        self.line_table.setColumnCount(5)
        self.line_table.setHorizontalHeaderLabels(["Customer", "Item", "Pallets", "Karton/Pal", ""])
        self.line_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.line_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.line_table.verticalHeader().setVisible(False)
        self.line_table.itemChanged.connect(self._on_line_changed)
        main_layout.addWidget(self.line_table, 3)

        self.route_list = QListWidget(self)
        self.route_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.route_list.model().rowsMoved.connect(self._on_route_reordered)  # type: ignore[arg-type]

        preview_layout = QVBoxLayout()
        preview_layout.addWidget(QLabel("Route preview"))
        preview_layout.addWidget(self.route_list)

        actions_layout = QHBoxLayout()
        self.estimate_button = QPushButton("Estimate route", self)
        self.export_button = QPushButton("Export to Excel", self)
        self.route_status_label = QLabel("", self)
        actions_layout.addWidget(self.estimate_button)
        actions_layout.addWidget(self.export_button)
        actions_layout.addStretch()
        actions_layout.addWidget(self.route_status_label)
        preview_layout.addLayout(actions_layout)
        main_layout.addLayout(preview_layout, 2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self.add_line_button.clicked.connect(self.add_line)
        self.remove_line_button.clicked.connect(self.remove_line)
        self.estimate_button.clicked.connect(self.estimate_route)
        self.export_button.clicked.connect(self.export_route)
        self.add_line_button.setEnabled(bool(self.customers) and bool(self.items))

        self.lines: List[OrderLineEntry] = []
        self.route_order: List[int] = []
        self.current_stops: List[Stop] = []
        self.stop_index_to_customer: Dict[int, Customer] = {}
        self.route_thread: Optional[QThread] = None
        self.route_worker: Optional[RouteCalculationWorker] = None
        self._line_table_updates_blocked = False
        if self.order:
            self._populate_from_order()
        self._select_order_warehouse()

    @property
    def customers(self) -> List[Customer]:
        return self.customers_all

    def _select_order_warehouse(self) -> None:
        if not self.order:
            return
        target_id = self.order.warehouse_id
        for idx in range(self.warehouse_combo.count()):
            warehouse: Optional[Warehouse] = self.warehouse_combo.itemData(idx)
            if warehouse and warehouse.id == target_id:
                self.warehouse_combo.setCurrentIndex(idx)
                break

    def _populate_from_order(self) -> None:
        if not self.order or not self.order.id:
            return
        customers_by_id = {customer.id: customer for customer in self.customers_all if customer.id is not None}
        items_by_id = {item.id: item for item in self.items if item.id is not None}
        missing_references = False
        for record in self.db.list_order_lines(self.order.id):
            customer = customers_by_id.get(record.customer_id)
            item = items_by_id.get(record.item_id)
            if not customer or not item:
                missing_references = True
                continue
            entry = OrderLineEntry(
                customer=customer,
                item=item,
                pallets=record.pallets,
                ktn_per_pal=record.ktn_per_pal if record.ktn_per_pal is not None else item.ktn_per_pal,
            )
            self.lines.append(entry)
            self._insert_line_row(entry)
        if missing_references:
            QMessageBox.warning(
                self,
                "Missing references",
                "Some order lines reference customers or items that no longer exist and were skipped.",
            )
        self._invalidate_route_preview()

    def _invalidate_route_preview(self) -> None:
        self.current_stops = []
        self.route_order = []
        self.route_list.clear()
        self.export_button.setEnabled(False)
        self.route_status_label.clear()

    def _insert_line_row(self, entry: OrderLineEntry) -> None:
        row = self.line_table.rowCount()
        self._line_table_updates_blocked = True
        try:
            self.line_table.insertRow(row)
            self.line_table.setItem(row, 0, self._create_line_table_item(entry.customer.name))
            self.line_table.setItem(row, 1, self._create_line_table_item(entry.item.name))
            self.line_table.setItem(
                row,
                2,
                self._create_line_table_item(self._format_pallets(entry.pallets), editable=True),
            )
            self.line_table.setItem(
                row,
                3,
                self._create_line_table_item(self._format_optional(entry.ktn_per_pal), editable=True),
            )
        finally:
            self._line_table_updates_blocked = False
        remove_btn = QPushButton("Remove", self.line_table)
        remove_btn.clicked.connect(lambda _, btn=remove_btn: self._remove_line_via_button(btn))
        self.line_table.setCellWidget(row, 4, remove_btn)

    def _create_line_table_item(self, text: str, editable: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        self._apply_line_item_flags(item, editable)
        return item

    def _apply_line_item_flags(self, item: QTableWidgetItem, editable: bool) -> None:
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        item.setFlags(flags)

    @staticmethod
    def _format_pallets(value: float) -> str:
        text = f"{value:.2f}"
        stripped = text.rstrip("0").rstrip(".")
        return stripped if stripped else "0"

    def _format_optional(self, value: Optional[float]) -> str:
        if value is None:
            return "-"
        return self._format_pallets(value)

    def add_line(self):
        if not self.customers or not self.items:
            QMessageBox.warning(self, "Missing data", "Define at least one customer and one item first.")
            return
        dialog = OrderLineDialog(self.customers, self.items, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for entry in dialog.selected_lines:
            self.lines.append(entry)
            self._insert_line_row(entry)
        self._invalidate_route_preview()

    def _remove_line_at(self, row: int) -> None:
        if row < 0 or row >= len(self.lines):
            return
        self.lines.pop(row)
        self.line_table.removeRow(row)
        self._invalidate_route_preview()

    def _on_line_changed(self, item: QTableWidgetItem) -> None:
        if self._line_table_updates_blocked:
            return
        row = item.row()
        col = item.column()
        if row >= len(self.lines):
            return
        entry = self.lines[row]
        text = item.text().strip()

        def reject(message: str) -> None:
            QMessageBox.warning(self, "Invalid value", message)

        if col == 2:
            try:
                pallets = float(text)
            except ValueError:
                reject("Pallet count must be a number.")
                return
            if pallets <= 0:
                reject("Pallet count must be greater than zero.")
                return
            entry.pallets = pallets
        elif col == 3:
            if not text or text == "-":
                entry.ktn_per_pal = None
            else:
                try:
                    ktn = float(text)
                except ValueError:
                    reject("Karton per pallet must be a number.")
                    return
                if ktn <= 0:
                    reject("Karton per pallet must be greater than zero.")
                    return
                entry.ktn_per_pal = ktn
        else:
            self._update_line_row(row, entry)
            return

        self._update_line_row(row, entry)
        self._invalidate_route_preview()

    def _update_line_row(self, row: int, entry: OrderLineEntry) -> None:
        self._line_table_updates_blocked = True
        try:
            # Ensure QTableWidgetItem exists for each column before updating text.
            item0 = self.line_table.item(row, 0)
            if item0 is None:
                item0 = self._create_line_table_item(entry.customer.name)
                self.line_table.setItem(row, 0, item0)

            item1 = self.line_table.item(row, 1)
            if item1 is None:
                item1 = self._create_line_table_item(entry.item.name)
                self.line_table.setItem(row, 1, item1)

            item2 = self.line_table.item(row, 2)
            if item2 is None:
                item2 = self._create_line_table_item(self._format_pallets(entry.pallets), editable=True)
                self.line_table.setItem(row, 2, item2)

            item3 = self.line_table.item(row, 3)
            if item3 is None:
                item3 = self._create_line_table_item(self._format_optional(entry.ktn_per_pal), editable=True)
                self.line_table.setItem(row, 3, item3)

            item0.setText(entry.customer.name)
            item1.setText(entry.item.name)
            item2.setText(self._format_pallets(entry.pallets))
            item3.setText(self._format_optional(entry.ktn_per_pal))
        finally:
            self._line_table_updates_blocked = False

    def _on_route_reordered(self) -> None:
        new_order: List[int] = []
        for idx in range(self.route_list.count()):
            item = self.route_list.item(idx)
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, int):
                new_order.append(data)
        self.route_order = new_order

    def _remove_line_via_button(self, button: QPushButton) -> None:
        for row in range(self.line_table.rowCount()):
            widget = self.line_table.cellWidget(row, 4)
            if widget is button:
                self._remove_line_at(row)
                break

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
            customer = entry.customer
            if customer.lat is None or customer.lng is None:
                raise ValueError(
                    f"Customer '{customer.name}' is missing latitude/longitude. Please update the customer before routing."
                )
            stops.append(Stop(name=customer.name, lat=customer.lat, lng=customer.lng))
            self.stop_index_to_customer[len(stops) - 1] = customer
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
        thread = QThread()
        _register_route_thread(thread)
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
                continue
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
        self.route_worker = None
        self.route_thread = None
        if self.route_status_label.text() == "Calculating route...":
            self.route_status_label.clear()

    def export_route(self):
        if not self.current_stops or not self.route_order:
            QMessageBox.warning(self, "Missing route", "Estimate the route before exporting.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export route to Excel",
            "",
            "Excel files (*.xlsx);;All files (*)",
        )
        if not path:
            return

        warehouse: Warehouse = self.warehouse_combo.currentData()
        if not warehouse:
            QMessageBox.warning(self, "Missing warehouse", "Select a warehouse before exporting.")
            return

        def _customer_key(customer: Customer) -> str:
            return customer.id or f"customer-{id(customer)}"

        customer_items: dict[str, List[RouteExcelItem]] = {}
        for entry in self.lines:
            key = _customer_key(entry.customer)
            customer_items.setdefault(key, [])
            ktn = entry.ktn_per_pal
            if ktn is None:
                ktn = entry.item.ktn_per_pal
            customer_items[key].append(
                RouteExcelItem(
                    item_name=entry.item.name,
                    pallets=entry.pallets,
                    cartons_per_pallet=ktn,
                )
            )

        rows: List[RouteExcelRow] = []
        for idx in self.route_order:
            customer = self.stop_index_to_customer.get(idx)
            if not customer:
                continue
            key = _customer_key(customer)
            rows.append(
                RouteExcelRow(
                    customer_name=customer.name,
                    address=customer.address,
                    items=list(customer_items.get(key, [])),
                    customer_id=customer.id,
                )
            )

        if not rows:
            QMessageBox.warning(self, "No route stops", "Add lines and estimate the route before exporting.")
            return

        order_date = self.order.created_at if (self.order and self.order.created_at) else datetime.now()
        total_pallets = sum(entry.pallets for entry in self.lines)
        try:
            export_route_to_excel(
                Path(path),
                rows,
                order_date=order_date,
                total_pallets=total_pallets,
                template_path=DEFAULT_TEMPLATE,
            )
        except Exception as exc:  # noqa: BLE001
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
        if self.order:
            order.id = self.order.id
            order.created_at = self.order.created_at
        order_lines: List[OrderLine] = []
        for entry in self.lines:
            assert entry.customer.id is not None
            assert entry.item.id is not None
            order_lines.append(
                OrderLine(
                    order_id=self.order.id if self.order and self.order.id else "",
                    customer_id=entry.customer.id,
                    item_id=entry.item.id,
                    pallets=entry.pallets,
                    ktn_per_pal=entry.ktn_per_pal,
                )
            )
        return order, order_lines

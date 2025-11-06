"""
GUI entry point for the Truck Route desktop application.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QThread, Signal
from PySide6.QtGui import QDoubleValidator
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
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView
)

from TruckRouteApp.db import init_db
from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.logic.export_excel import DEFAULT_TEMPLATE, RouteExcelRow, export_route_to_excel
from TruckRouteApp.logic.routing_local import Stop, RouteResult, haversine_meters, optimise_route
from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse


class ColumnConfig:
    """Model column definition coupling header text with a value extractor."""

    def __init__(self, header: str, extractor: Callable):
        self.header = header
        self.extractor = extractor


class SQLModelTableModel(QAbstractTableModel):
    """
    Generic Qt table model that adapts SQLModel rows for presentation.
    Column descriptors supply both header labels and value extraction logic.
    """

    def __init__(self, columns: Sequence[ColumnConfig], parent=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: List = []

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
            return self._columns[section].header
        return section + 1

    def get_row(self, index: QModelIndex):
        if not index.isValid():
            return None
        return self._rows[index.row()]


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


class CSVMappingDialog(QDialog):
    """
    Lets the user map CSV headers to application fields, enforcing uniqueness and
    allowing optional fields to be skipped.
    """

    def __init__(
        self,
        headers: Sequence[str],
        field_specs: Sequence[tuple[str, str, bool]],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Map CSV Columns")
        self.setMinimumWidth(480)
        self._combos: Dict[str, QComboBox] = {}
        self._required: Dict[str, bool] = {}
        self._mapping: Dict[str, Optional[str]] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for field, label, required in field_specs:
            combo = QComboBox(self)
            combo.addItem("<Skip>", "")
            for header in headers:
                combo.addItem(header, header)
            combo.setMinimumWidth(260)
            self._combos[field] = combo
            self._required[field] = required
            display_label = f"{label}{' *' if required else ''}"
            form.addRow(display_label, combo)
            self._auto_select_default(combo, field, label, headers)

        layout.addLayout(form)

        note = QLabel("Select the CSV column for each field. Fields marked * are required.")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _auto_select_default(self, combo: QComboBox, field: str, label: str, headers: Sequence[str]) -> None:
        """Pre-select a column whose name best matches the target field label."""
        candidates = {
            field.lower(),
            label.lower(),
            label.lower().replace(" ", "_"),
        }
        for index in range(1, combo.count()):
            header = combo.itemText(index)
            if header.lower() in candidates:
                combo.setCurrentIndex(index)
                return

    def _handle_accept(self) -> None:
        """Validate selections and persist them before closing the dialog."""
        mapping: Dict[str, Optional[str]] = {}
        used_columns: set[str] = set()
        for field, combo in self._combos.items():
            column = combo.currentData()
            required = self._required[field]
            if required and not column:
                QMessageBox.warning(self, "Invalid mapping", f"Field '{field}' is required.")
                return
            if column:
                if column in used_columns:
                    QMessageBox.warning(self, "Invalid mapping", f"Column '{column}' is assigned multiple times.")
                    return
                used_columns.add(column)
            mapping[field] = column or None
        self._mapping = mapping
        self.accept()

    def get_mapping(self) -> Optional[Dict[str, Optional[str]]]:
        """Return the validated mapping once the dialog has been accepted."""
        if self.exec() != QDialog.DialogCode.Accepted:
            return None
        return self._mapping


class WarehouseDialog(QDialog):
    """Modal editor for creating or updating a single warehouse record."""

    def __init__(self, warehouse: Optional[Warehouse] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Warehouse")
        self.setMinimumWidth(420)
        self.warehouse = warehouse or Warehouse(name="", lat=0.0, lng=0.0)

        form = QFormLayout(self)
        self.name_edit = QLineEdit(self.warehouse.name, self)
        self.name_edit.setMinimumWidth(300)
        self.address_edit = QLineEdit(self.warehouse.address or "", self)
        self.address_edit.setMinimumWidth(300)
        self.lat_edit = QLineEdit(
            "" if self.warehouse.lat is None else str(self.warehouse.lat),
            self,
        )
        self.lat_edit.setMinimumWidth(140)
        self.lng_edit = QLineEdit(
            "" if self.warehouse.lng is None else str(self.warehouse.lng),
            self,
        )
        self.lng_edit.setMinimumWidth(140)
        form.addRow("Name", self.name_edit)
        form.addRow("Address", self.address_edit)
        form.addRow("Latitude", self.lat_edit)
        form.addRow("Longitude", self.lng_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> Optional[Warehouse]:
        """
        Present the dialog until valid numeric coordinates are entered.
        Returns the updated warehouse or None if the dialog was cancelled.
        """
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
    """Modal editor for customer records with optional coordinates."""

    def __init__(self, customer: Optional[Customer] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customer")
        self.setMinimumWidth(420)  # widen the dialog for better readability
        self.customer = customer or Customer(name="", lat=0.0, lng=0.0)

        form = QFormLayout(self)
        self.id_edit = QLineEdit("" if self.customer.id is None else str(self.customer.id), self)
        self.id_edit.setMinimumWidth(200)
        if self.customer.id is not None:
            self.id_edit.setReadOnly(True)
        else:
            self.id_edit.setPlaceholderText("Required")
        form.addRow("ID", self.id_edit)

        self.name_edit = QLineEdit(self.customer.name, self)
        self.name_edit.setMinimumWidth(300)
        self.address_edit = QLineEdit(self.customer.address or "", self)
        self.address_edit.setMinimumWidth(300)
        self.lat_edit = QLineEdit(
            "" if self.customer.lat is None else str(self.customer.lat),
            self,
        )
        self.lat_edit.setMinimumWidth(300)
        self.lng_edit = QLineEdit(
            "" if self.customer.lng is None else str(self.customer.lng),
            self,
        )
        self.lng_edit.setMinimumWidth(300)
        form.addRow("Name", self.name_edit)
        form.addRow("Address", self.address_edit)
        form.addRow("Latitude", self.lat_edit)
        form.addRow("Longitude", self.lng_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> Optional[Customer]:
        """
        Display the dialog until the submitted latitude/longitude values are valid.
        Returns the updated customer or None when cancelled.
        """
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None
            lat_text = self.lat_edit.text().strip()
            lng_text = self.lng_edit.text().strip()
            try:
                lat = float(lat_text) if lat_text else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Latitude must be a numeric value.")
                continue
            try:
                lng = float(lng_text) if lng_text else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Longitude must be a numeric value.")
                continue
            id_text = self.id_edit.text().strip()
            if not id_text and self.customer.id is None:
                QMessageBox.warning(self, "Validation error", "ID is required.")
                continue
            if id_text:
                self.customer.id = id_text
            self.customer.name = self.name_edit.text()
            self.customer.address = self.address_edit.text()
            self.customer.lat = lat
            self.customer.lng = lng
            return self.customer


class ItemDialog(QDialog):
    """Modal editor for product items with optional packaging and pricing metadata."""

    def __init__(self, item: Optional[Item] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Item")
        self.setMinimumWidth(460)
        self.item = item or Item(name="")

        form = QFormLayout(self)
        self.id_edit = QLineEdit("" if self.item.id is None else str(self.item.id), self)
        self.id_edit.setMinimumWidth(160)
        if self.item.id is not None:
            self.id_edit.setReadOnly(True)
        else:
            self.id_edit.setPlaceholderText("Required")
        form.addRow("ID", self.id_edit)

        self.name_edit = QLineEdit(self.item.name, self)
        self.name_edit.setMinimumWidth(300)
        self.ktn_per_pal_edit = QLineEdit(
            "" if self.item.ktn_per_pal is None else str(self.item.ktn_per_pal),
            self,
        )
        self.ktn_per_pal_edit.setMinimumWidth(160)
        self.items_per_ktn_edit = QLineEdit(
            "" if self.item.items_per_ktn is None else self.item.items_per_ktn,
            self,
        )
        self.items_per_ktn_edit.setMinimumWidth(160)
        self.price_gross_edit = QLineEdit(
            "" if self.item.price_gross is None else str(self.item.price_gross),
            self,
        )
        self.price_gross_edit.setMinimumWidth(160)
        self.price_net_edit = QLineEdit(
            "" if self.item.price_net is None else str(self.item.price_net),
            self,
        )
        self.price_net_edit.setMinimumWidth(160)
        self.tax_edit = QLineEdit(
            "" if self.item.tax is None else self.item.tax,
            self,
        )
        self.tax_edit.setMinimumWidth(160)
        form.addRow("Name", self.name_edit)
        form.addRow("KTN per Pal", self.ktn_per_pal_edit)
        form.addRow("Items per KTN", self.items_per_ktn_edit)
        form.addRow("Price (gross)", self.price_gross_edit)
        form.addRow("Price (net)", self.price_net_edit)
        form.addRow("Tax", self.tax_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_data(self) -> Optional[Item]:
        """
        Persist user edits after validating numeric fields.
        Returns the updated item or None if the dialog was cancelled.
        """
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None

            id_text = self.id_edit.text().strip()
            if not id_text:
                QMessageBox.warning(self, "Validation error", "ID is required.")
                continue

            try:
                ktn_per_pal = int(self.ktn_per_pal_edit.text()) if self.ktn_per_pal_edit.text().strip() else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "KTN per Pal must be an integer.")
                continue

            items_per_ktn_text = self.items_per_ktn_edit.text().strip()
            items_per_ktn = items_per_ktn_text if items_per_ktn_text else None

            try:
                price_gross = float(self.price_gross_edit.text()) if self.price_gross_edit.text().strip() else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Price (gross) must be numeric.")
                continue

            try:
                price_net = float(self.price_net_edit.text()) if self.price_net_edit.text().strip() else None
            except ValueError:
                QMessageBox.warning(self, "Validation error", "Price (net) must be numeric.")
                continue

            tax_text = self.tax_edit.text().strip()
            tax = tax_text if tax_text else None

            self.item.id = id_text
            self.item.name = self.name_edit.text()
            self.item.ktn_per_pal = ktn_per_pal
            self.item.items_per_ktn = items_per_ktn
            self.item.price_gross = price_gross
            self.item.price_net = price_net
            self.item.tax = tax
            return self.item


class WarehouseView(BaseCrudView):
    """CRUD view presenting warehouses and handling create/edit/delete actions."""

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
        
        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)   # strech address column

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        
        self.refresh()

    def refresh(self):
        """Reload the warehouse table from the database."""
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
    """CRUD view for customer records, including CSV import support."""

    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        columns = [
            ColumnConfig("ID", lambda c: c.id),
            ColumnConfig("Name", lambda c: c.name),
            ColumnConfig("Address", lambda c: c.address or ""),
            ColumnConfig("Latitude", lambda c: c.lat if c.lat is not None else ""),
            ColumnConfig("Longitude", lambda c: c.lng if c.lng is not None else ""),
        ]
        self.model = SQLModelTableModel(columns, self)
        self.set_model(self.model)
        self.refresh()
        
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(100)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)   # stretch Name column
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # stretch Address column

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        self.import_button = QPushButton("Import CSV", self)
        self.button_bar.insertWidget(3, self.import_button)
        self.import_button.clicked.connect(self.import_csv)

    @staticmethod
    def _open_sniffed_reader(fh) -> csv.DictReader:
        sample = fh.read(2048)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";"
        return csv.DictReader(fh, delimiter=delimiter)

    def refresh(self):
        """Refresh the customer list from persistent storage."""
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

    def import_csv(self):
        """Import customers from a CSV file, skipping duplicates and quiet errors."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import customers from CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = self._open_sniffed_reader(fh)
                headers = reader.fieldnames
                if not headers:
                    raise ValueError("CSV file must include a header row.")
                mapping_dialog = CSVMappingDialog(
                    headers,
                    [
                        ("id", "ID", True),
                        ("name", "Name", True),
                        ("address", "Address", False),
                        ("lat", "Latitude", True),
                        ("lng", "Longitude", True),
                    ],
                    self,
                )
                mapping = mapping_dialog.get_mapping()
                if not mapping:
                    return
                id_col = mapping["id"]
                name_col = mapping["name"]
                address_col = mapping.get("address")
                lat_col = mapping["lat"]
                lng_col = mapping["lng"]
                for row in reader:
                    if not any(row.values()):
                        continue
                    try:
                        id_value = (row.get(id_col) or "").strip()
                        if not id_value:
                            raise ValueError("missing id")
                        name = (row.get(name_col) or "").strip()
                        if not name:
                            raise ValueError("missing name")
                        lat = None
                        lng = None
                        if lat_col:
                            lat_str = (row.get(lat_col) or "").strip()
                            if lat_str:
                                lat = float(lat_str)
                        if lng_col:
                            lng_str = (row.get(lng_col) or "").strip()
                            if lng_str:
                                lng = float(lng_str)
                        address_value = (row.get(address_col) or "").strip() if address_col else ""
                        address = address_value or None
                        if self.db.customer_exists(name, address):
                            continue
                        customer = Customer(id=id_value, name=name, address=address, lat=lat, lng=lng)
                        self.db.save_customer(customer)
                    except Exception:  # noqa: BLE001
                        # Rows with format issues are ignored silently; only critical errors are shown.
                        continue
                self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import error", str(exc))


class ItemView(BaseCrudView):
    """CRUD view for items with optional CSV import into the catalog."""

    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        columns = [
            ColumnConfig("ID", lambda item: item.id),
            ColumnConfig("Name", lambda item: item.name),
            ColumnConfig("KTN/pal", lambda item: item.ktn_per_pal or ""),
            ColumnConfig("Items/KTN", lambda item: item.items_per_ktn or ""),
            ColumnConfig("Price (gross)", lambda item: f"{item.price_gross:.2f}" if item.price_gross is not None else ""),
            ColumnConfig("Price (net)", lambda item: f"{item.price_net:.2f}" if item.price_net is not None else ""),
            ColumnConfig("Tax", lambda item: item.tax or ""),
        ]
        self.model = SQLModelTableModel(columns, self)
        self.set_model(self.model)
        self.refresh()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # stretch Name column

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        self.import_button = QPushButton("Import CSV", self)
        self.button_bar.insertWidget(3, self.import_button)
        self.import_button.clicked.connect(self.import_csv)

    def refresh(self):
        """Refresh the items table with the latest records."""
        self.model.set_rows(self.db.list_items())
        self.table.resizeColumnsToContents()

    @staticmethod
    def _open_sniffed_reader(fh) -> csv.DictReader:
        sample = fh.read(2048)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";"
        return csv.DictReader(fh, delimiter=delimiter)

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

    def import_csv(self):
        """Import item records from CSV, capturing row-level issues for the user."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import items from CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = self._open_sniffed_reader(fh)
                headers = reader.fieldnames
                if not headers:
                    raise ValueError("CSV file must include a header row.")
                mapping_dialog = CSVMappingDialog(
                    headers,
                    [
                        ("id", "ID", True),
                        ("name", "Name", True),
                        ("ktn_per_pal", "KTN per Pal", False),
                        ("items_per_ktn", "Items per KTN", False),
                        ("price_gross", "Price (gross)", False),
                        ("price_net", "Price (net)", False),
                        ("tax", "Tax", False),
                    ],
                    self,
                )
                mapping = mapping_dialog.get_mapping()
                if not mapping:
                    return
                id_col = mapping["id"]
                name_col = mapping["name"]
                ktn_col = mapping.get("ktn_per_pal")
                items_col = mapping.get("items_per_ktn")
                price_gross_col = mapping.get("price_gross")
                price_net_col = mapping.get("price_net")
                tax_col = mapping.get("tax")
                imported = 0
                skipped = 0
                errors: List[str] = []
                for row_num, row in enumerate(reader, start=2):
                    if not any(row.values()):
                        continue
                    try:
                        id_value = (row.get(id_col) or "").strip()
                        if not id_value:
                            raise ValueError("missing id")
                        item_id = id_value
                        name = (row.get(name_col) or "").strip()
                        if not name:
                            raise ValueError("missing name")
                        ktn_per_pal = None
                        if ktn_col:
                            ktn_str = (row.get(ktn_col) or "").strip()
                            if ktn_str:
                                ktn_per_pal = int(float(ktn_str))
                        items_per_ktn = None
                        if items_col:
                            items_str = (row.get(items_col) or "").strip()
                            if items_str:
                                items_per_ktn = items_str
                        price_gross = None
                        if price_gross_col:
                            gross_str = (row.get(price_gross_col) or "").strip()
                            if gross_str:
                                price_gross = float(gross_str)
                        price_net = None
                        if price_net_col:
                            net_str = (row.get(price_net_col) or "").strip()
                            if net_str:
                                price_net = float(net_str)
                        tax = None
                        if tax_col:
                            tax_str = (row.get(tax_col) or "").strip()
                            if tax_str:
                                tax = tax_str
                        item = Item(
                            id=item_id,
                            name=name,
                            ktn_per_pal=ktn_per_pal,
                            items_per_ktn=items_per_ktn,
                            price_gross=price_gross,
                            price_net=price_net,
                            tax=tax,
                        )
                        self.db.save_item(item)
                        imported += 1
                    except Exception as exc:  # noqa: BLE001
                        skipped += 1
                        errors.append(f"Row {row_num}: {exc}")
                self.refresh()
                summary = f"Imported {imported} item(s)."
                if skipped:
                    summary += f" Skipped {skipped} row(s)."
                if errors:
                    details = "\n".join(errors[:5])
                    if len(errors) > 5:
                        details += "\n..."
                    QMessageBox.warning(self, "Import completed with issues", summary + "\n\n" + details)
                else:
                    QMessageBox.information(self, "Import complete", summary)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Import error", str(exc))


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
        except Exception as exc:  # propagate error to GUI thread
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
        self._item_rows: List[dict[str, object]] = []

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
            "pallet_input": pallets_input,
            "karton_input": karton_input,
        }
        self._item_rows.append(row)
        item_combo.currentIndexChanged.connect(lambda _: self._update_row_karton(row))
        self._update_row_karton(row)
        self._update_remove_button_state()

    def _remove_item_row(self) -> None:
        if len(self._item_rows) <= 1:
            return
        row = self._item_rows.pop()
        widget: QWidget = row["widget"]  # type: ignore[assignment]
        widget.setParent(None)
        widget.deleteLater()
        self._update_remove_button_state()

    def _update_remove_button_state(self) -> None:
        self.remove_item_button.setEnabled(len(self._item_rows) > 1)

    def _update_row_karton(self, row: dict[str, object]) -> None:
        item_combo: QComboBox = row["item_combo"]  # type: ignore[assignment]
        karton_input: QLineEdit = row["karton_input"]  # type: ignore[assignment]
        item: Optional[Item] = item_combo.currentData()
        if item and item.ktn_per_pal is not None:
            karton_input.setPlaceholderText(str(item.ktn_per_pal))
        else:
            karton_input.setPlaceholderText("")

    def _handle_accept(self) -> None:
        customer = self.customer_combo.currentData()
        if customer is None:
            QMessageBox.warning(self, "Missing selection", "Please choose a customer.")
            return
        if not self._item_rows:
            QMessageBox.warning(self, "Missing items", "Add at least one product line.")
            return

        collected: List[OrderLineEntry] = []
        for index, row in enumerate(self._item_rows, start=1):
            item_combo: QComboBox = row["item_combo"]  # type: ignore[assignment]
            pallets_edit: QLineEdit = row["pallet_input"]  # type: ignore[assignment]
            karton_edit: QLineEdit = row["karton_input"]  # type: ignore[assignment]
            item: Optional[Item] = item_combo.currentData()
            if item is None:
                QMessageBox.warning(
                    self,
                    "Missing item",
                    f"Select a product for line {index}.",
                )
                return
            pallets_text = pallets_edit.text().strip()
            if not pallets_text:
                QMessageBox.warning(
                    self,
                    "Missing pallets",
                    f"Enter the number of pallets for '{item.name}' (line {index}).",
                )
                return
            try:
                pallets = float(pallets_text)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid value",
                    f"Pallet count must be numeric for '{item.name}' (line {index}).",
                )
                return
            if pallets <= 0:
                QMessageBox.warning(
                    self,
                    "Invalid value",
                    f"Pallet count must be greater than zero for '{item.name}' (line {index}).",
                )
                return
            default_ktn = item.ktn_per_pal
            karton_text = karton_edit.text().strip()
            if karton_text:
                try:
                    ktn_value = float(karton_text)
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid value",
                        f"Karton per pallet must be numeric for '{item.name}' (line {index}).",
                    )
                    return
                if ktn_value <= 0:
                    QMessageBox.warning(
                        self,
                        "Invalid value",
                        f"Karton per pallet must be greater than zero for '{item.name}' (line {index}).",
                    )
                    return
            else:
                if default_ktn is None:
                    QMessageBox.warning(
                        self,
                        "Missing value",
                        f"Item '{item.name}' does not define Karton per pallet. Please enter a value for line {index}.",
                    )
                    return
                ktn_value = float(default_ktn)
            collected.append(
                OrderLineEntry(customer=customer, item=item, pallets=pallets, ktn_per_pal=ktn_value)
            )

        self.selected_lines = collected
        self.accept()

    def get_lines(self) -> List[OrderLineEntry]:
        """Return the list of collected order line entries."""
        if self.exec() != QDialog.DialogCode.Accepted:
            return []
        return self.selected_lines


class OrderDialog(QDialog):
    """
    Multi-step wizard for building an order: choose warehouse, add lines, preview
    the route, and optionally export to Excel before confirming.
    """

    def __init__(self, db: DatabaseService, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Create Order")
        self.resize(720, 500)
        self.setMinimumWidth(900)

        self.warehouses = self.db.list_warehouses()
        self.customers_all = self.db.list_customers()
        self.customers = [c for c in self.customers_all if c.lat is not None and c.lng is not None]
        self.customers_missing_coords = [c for c in self.customers_all if c.lat is None or c.lng is None]
        self.items = self.db.list_items()

        if not self.warehouses:
            QMessageBox.warning(self, "Missing data", "Please create at least one warehouse first.")
        if not self.customers_all:
            QMessageBox.warning(self, "Missing data", "Please create at least one customer first.")
        elif not self.customers:
            QMessageBox.warning(
                self,
                "Missing coordinates",
                "No customers have latitude/longitude set. Please update customer records before creating an order.",
            )
        elif self.customers_missing_coords:
            limited = ", ".join(c.name for c in self.customers_missing_coords[:5])
            ellipsis = "..." if len(self.customers_missing_coords) > 5 else ""
            QMessageBox.information(
                self,
                "Customers excluded",
                f"The following customers are missing coordinates and cannot be added to this order: {limited}{ellipsis}",
            )
        if not self.items:
            QMessageBox.warning(self, "Missing data", "Please create at least one item first.")

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        layout.addLayout(form_layout)

        self.warehouse_combo = QComboBox(self)
        for warehouse in self.warehouses:
            self.warehouse_combo.addItem(warehouse.name, warehouse)
        self.warehouse_combo.setMinimumWidth(260)
        form_layout.addRow("Warehouse", self.warehouse_combo)

        self.line_table = QTableWidget(0, 5, self)
        self.line_table.setHorizontalHeaderLabels(["Customer", "Product", "Pallets", "Karton/Pal", ""])
        self.line_table.horizontalHeader().setStretchLastSection(False)
        self.line_table.setMinimumWidth(600)
        header = self.line_table.horizontalHeader()
        header.setMinimumSectionSize(150)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)   # stretch Product column
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.line_table.setColumnWidth(2, 120)
        self.line_table.setColumnWidth(3, 140)
        self.line_table.setColumnWidth(4, 110)
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
        self.route_list.setMinimumWidth(300)
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
        self.add_line_button.setEnabled(bool(self.customers) and bool(self.items))

        self.lines: List[OrderLineEntry] = []
        self.route_order: List[int] = []  # customer IDs in the order list
        self.current_stops: List[Stop] = []
        self.stop_index_to_customer: dict[int, Customer] = {}
        self.route_thread: Optional[QThread] = None
        self.route_worker: Optional[RouteCalculationWorker] = None

    @staticmethod
    def _format_pallets(value: float) -> str:
        """Format pallet counts for display, trimming superfluous zeros and dots."""
        text = f"{value:.2f}"
        stripped = text.rstrip("0").rstrip(".")
        return stripped if stripped else "0"

    def _format_optional(self, value: Optional[float]) -> str:
        """Format optional numeric values, returning '-' when not provided."""
        if value is None:
            return "-"
        return self._format_pallets(float(value))

    def _format_line_summary(self, entry: OrderLineEntry) -> str:
        """Compose a human-readable summary for exports and previews."""
        parts = [f"{entry.item.name}: {self._format_pallets(entry.pallets)} Pal"]
        ktn = entry.ktn_per_pal
        if ktn is not None:
            parts.append(f"{self._format_optional(ktn)} Ktn/Pal")
        return " / ".join(parts)

    def add_line(self):
        """Add a new line or overwrite an existing one for the same customer/item pair."""
        if not self.customers:
            QMessageBox.warning(
                self,
                "No eligible customers",
                "All customers are missing coordinates. Please update customer records before adding lines.",
            )
            return
        dialog = OrderLineDialog(self.customers, self.items, self)
        entries = dialog.get_lines()
        if not entries:
            return
        for entry in entries:
            key = (entry.customer.id, entry.item.id)
            existing_index: Optional[int] = None
            for idx, line in enumerate(self.lines):
                if (line.customer.id, line.item.id) == key:
                    existing_index = idx
                    break

            if existing_index is not None:
                self.lines[existing_index] = entry
                self._update_line_row(existing_index, entry)
            else:
                self.lines.append(entry)
                row = self.line_table.rowCount()
                self.line_table.insertRow(row)
                self.line_table.setItem(row, 0, QTableWidgetItem(entry.customer.name))
                self.line_table.setItem(row, 1, QTableWidgetItem(entry.item.name))
                self.line_table.setItem(row, 2, QTableWidgetItem(self._format_pallets(entry.pallets)))
                self.line_table.setItem(row, 3, QTableWidgetItem(self._format_optional(entry.ktn_per_pal)))
                remove_btn = QPushButton("Remove", self.line_table)
                remove_btn.clicked.connect(lambda _, btn=remove_btn: self._remove_line_via_button(btn))
                self.line_table.setCellWidget(row, 4, remove_btn)

        self.route_list.clear()
        self.export_button.setEnabled(False)
        self.route_status_label.clear()

    def _update_line_row(self, row: int, entry: OrderLineEntry) -> None:
        """Refresh the UI table cells to mirror the provided order line entry."""
        values = [
            entry.customer.name,
            entry.item.name,
            self._format_pallets(entry.pallets),
            self._format_optional(entry.ktn_per_pal),
        ]
        for col, value in enumerate(values):
            item = self.line_table.item(row, col)
            if item is None:
                self.line_table.setItem(row, col, QTableWidgetItem(value))
            else:
                item.setText(value)

    def _remove_line_at(self, row: int):
        """Remove a row from both state and table, clearing stale route previews."""
        if 0 <= row < len(self.lines):
            self.lines.pop(row)
            self.line_table.removeRow(row)
        self.route_list.clear()
        self.export_button.setEnabled(False)
        self.route_status_label.clear()

    def _remove_line_via_button(self, button: QPushButton) -> None:
        """Delete the table row associated with a remove button."""
        for row in range(self.line_table.rowCount()):
            widget = self.line_table.cellWidget(row, 4)
            if widget is button:
                self._remove_line_at(row)
                break

    def remove_line(self):
        """Delete the currently selected order line, if any."""
        row = self.line_table.currentRow()
        if row >= 0:
            self._remove_line_at(row)

    def _build_stops(self) -> Optional[List[Stop]]:
        """Translate order lines into a stop list suitable for the routing engine."""
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
                raise ValueError(f"Customer '{customer.name}' is missing latitude/longitude. Please update the customer before routing.")
            stops.append(Stop(name=customer.name, lat=customer.lat, lng=customer.lng))
            self.stop_index_to_customer[len(stops) - 1] = customer
        return stops

    def estimate_route(self):
        """Kick off background route optimisation and update the UI state."""
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
        """Handle background routing completion, updating the list or surfacing errors."""
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
        """Render the computed route into the preview widget and store ordering."""
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
        """Reset thread references once the worker completes or aborts."""
        self.route_thread = None
        if self.route_status_label.text() == "Calculating route...":
            self.route_status_label.clear()

    def export_route(self):
        """Convert the current previewed route into an Excel workbook."""
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
        lines_by_customer: dict[str, List[OrderLineEntry]] = {}
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
                        self._format_line_summary(line)
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
        """Validate order prerequisites before letting the dialog close successfully."""
        if not self.lines:
            QMessageBox.warning(self, "Missing lines", "Add at least one order line.")
            return
        warehouse: Optional[Warehouse] = self.warehouse_combo.currentData()
        if not warehouse:
            QMessageBox.warning(self, "Missing warehouse", "Select a warehouse.")
            return
        super().accept()

    def get_payload(self) -> Optional[tuple[Order, List[OrderLine]]]:
        """Execute the dialog and, on success, return order and line models ready for saving."""
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
                    order_id="",
                    customer_id=entry.customer.id,
                    item_id=entry.item.id,
                    pallets=entry.pallets,
                )
            )
        return order, order_lines


class OrderView(BaseCrudView):
    """Read-only order list with actions to create and delete orders."""

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
                
        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _warehouse_name(self, order: Order):
        """Resolve the warehouse name lazily so we can display it in the table."""
        warehouse = self.db.get_warehouse(order.warehouse_id)
        return warehouse.name if warehouse else "Unknown"

    def refresh(self):
        """Reload the order listing, sorted by creation timestamp."""
        self.model.set_rows(self.db.list_orders())
        self.table.resizeColumnsToContents()

    def create_order(self):
        """Open the order dialog and persist the resulting order if confirmed."""
        dialog = OrderDialog(self.db, self)
        payload = dialog.get_payload()
        if not payload:
            return
        order, lines = payload
        self.db.create_order_with_lines(order, lines)
        self.refresh()

    def delete_order(self):
        """Prompt for confirmation before deleting the selected order."""
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


def main():
    """Initialise the database, spin up the Qt application, and start the event loop."""
    init_db()
    db_service = DatabaseService()
    app = QApplication(sys.argv)
    window = MainWindow(db_service)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

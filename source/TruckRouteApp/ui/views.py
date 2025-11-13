"""
Concrete CRUD views that compose the dialogs and table utilities.
"""

from __future__ import annotations

import csv
from typing import List, Optional

from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QAbstractItemView,
)

from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.models.schema import Customer, Item, Order, Warehouse
from TruckRouteApp.ui.base import BaseCrudView
from TruckRouteApp.ui.dialogs import CSVMappingDialog, CustomerDialog, ItemDialog, WarehouseDialog
from TruckRouteApp.ui.order_dialog import OrderDialog
from TruckRouteApp.ui.table_models import ColumnConfig, SQLModelTableModel
from TruckRouteApp.ui.i18n import i18n, tr


def _open_sniffed_reader(fh) -> csv.DictReader:
    sample = fh.read(2048)
    fh.seek(0)
    try:
        # Inspect the first chunk of the file so we can adapt to ";" vs "," delimited CSVs.
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ";"
    return csv.DictReader(fh, delimiter=delimiter)


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
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)

        self.refresh()

    def refresh(self):
        """Reload the warehouse table from the database."""
        # Table models are kept lightweight, so we just swap out their rows every time.
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
            tr("Delete warehouse"),
            tr("Delete warehouse '{name}'?").format(name=warehouse.name),
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
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        selection_model = self.table.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._update_action_states)
        self.refresh()

        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(100)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        self.import_button = QPushButton(self)
        self.button_bar.insertWidget(3, self.import_button)
        self.import_button.clicked.connect(self.import_csv)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()
        self._update_action_states()

    def refresh(self):
        """Refresh the customer list from persistent storage."""
        self.model.set_rows(self.db.list_customers())
        self.table.resizeColumnsToContents()
        self._update_action_states()

    def add(self):
        dialog = CustomerDialog(parent=self)
        result = dialog.get_data()
        if result:
            customer, original_id = result
            try:
                self.db.save_customer(customer, original_id=original_id)
            except ValueError as exc:
                self._show_customer_error(str(exc))
                return
            self.refresh()

    def edit(self):
        index = self.selected_index()
        if not index:
            return
        customer: Optional[Customer] = self.model.get_row(index)
        if not customer:
            return
        dialog = CustomerDialog(customer=customer, parent=self)
        result = dialog.get_data()
        if result:
            updated, original_id = result
            try:
                self.db.save_customer(updated, original_id=original_id or customer.id)
            except ValueError as exc:
                self._show_customer_error(str(exc))
                return
            self.refresh()

    def delete(self):
        indexes = self.selected_indexes()
        if not indexes:
            return
        customers = [
            self.model.get_row(index)
            for index in indexes
            if self.model
        ]
        customers = [c for c in customers if c]
        if not customers:
            return
        if len(customers) == 1:
            title = tr("Delete customer")
            message = tr("Delete customer '{name}'?").format(name=customers[0].name)
        else:
            title = tr("Delete customers")
            message = tr("Delete {count} selected customers?").format(count=len(customers))
        confirm = QMessageBox.question(self, title, message)
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_customers([customer.id for customer in customers])
            self.refresh()

    def import_csv(self):
        """Import customers from a CSV file, skipping duplicates and quiet errors."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Import customers from CSV"),
            "",
            tr("CSV files (*.csv);;All files (*)"),
        )
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = _open_sniffed_reader(fh)
                # CSVs coming from Excel often have BOMs – ``DictReader`` handles it via ``encoding="utf-8-sig"``.
                headers = reader.fieldnames
                if not headers:
                    raise ValueError(tr("CSV file must include a header row."))
                mapping_dialog = CSVMappingDialog(
                    headers,
                    [
                        ("id", "ID", False),
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
                id_col = mapping.get("id")
                name_col = mapping["name"]
                address_col = mapping.get("address")
                lat_col = mapping["lat"]
                lng_col = mapping["lng"]
                for row in reader:
                    if not any(row.values()):
                        continue
                    try:
                        # Normalize strings first so validation/duplicates work reliably.
                        id_value = (row.get(id_col) or "").strip() if id_col else ""
                        name = (row.get(name_col) or "").strip()
                        if not name:
                            raise ValueError(tr("missing name"))
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
                        customer = Customer(
                            id=id_value or None,
                            name=name,
                            address=address,
                            lat=lat,
                            lng=lng,
                        )
                        self.db.save_customer(customer)
                    except Exception:  # noqa: BLE001
                        # Invalid rows are ignored silently—showing a modal per issue would be too noisy.
                        continue
                self.refresh()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Import error"), str(exc))

    def _apply_translations(self) -> None:
        self.import_button.setText(tr("Import CSV"))

    def _update_action_states(self, *_args) -> None:
        selection_count = len(self.selected_indexes())
        self.edit_button.setEnabled(selection_count == 1)
        self.delete_button.setEnabled(selection_count >= 1)

    def _show_customer_error(self, code: str) -> None:
        if code == "duplicate_customer_id":
            message = tr("Customer ID already exists.")
        elif code == "customer_not_found":
            message = tr("Customer record could not be found.")
        else:
            message = code
        QMessageBox.warning(self, tr("Validation error"), message)


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
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        selection_model = self.table.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._update_action_states)
        self.refresh()

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        self.import_button = QPushButton(self)
        self.button_bar.insertWidget(3, self.import_button)
        self.import_button.clicked.connect(self.import_csv)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()
        self._update_action_states()

    def refresh(self):
        """Refresh the items table with the latest records."""
        self.model.set_rows(self.db.list_items())
        self.table.resizeColumnsToContents()
        self._update_action_states()

    def add(self):
        dialog = ItemDialog(parent=self)
        result = dialog.get_data()
        if result:
            item, original_id = result
            try:
                self.db.save_item(item, original_id=original_id)
            except ValueError as exc:
                self._show_item_error(str(exc))
                return
            self.refresh()

    def edit(self):
        index = self.selected_index()
        if not index:
            return
        item: Optional[Item] = self.model.get_row(index)
        if not item:
            return
        dialog = ItemDialog(item=item, parent=self)
        result = dialog.get_data()
        if result:
            updated, original_id = result
            try:
                self.db.save_item(updated, original_id=original_id or item.id)
            except ValueError as exc:
                self._show_item_error(str(exc))
                return
            self.refresh()

    def delete(self):
        indexes = self.selected_indexes()
        if not indexes:
            return
        items = [
            self.model.get_row(index)
            for index in indexes
            if self.model
        ]
        items = [item for item in items if item]
        if not items:
            return
        if len(items) == 1:
            title = tr("Delete item")
            message = tr("Delete item '{name}'?").format(name=items[0].name)
        else:
            title = tr("Delete items")
            message = tr("Delete {count} selected items?").format(count=len(items))
        confirm = QMessageBox.question(self, title, message)
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_items([item.id for item in items])
            self.refresh()

    def import_csv(self):
        """Import item records from CSV, capturing row-level issues for the user."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Import items from CSV"),
            "",
            tr("CSV files (*.csv);;All files (*)"),
        )
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                reader = _open_sniffed_reader(fh)
                headers = reader.fieldnames
                if not headers:
                    raise ValueError(tr("CSV file must include a header row."))
                mapping_dialog = CSVMappingDialog(
                    headers,
                    [
                        ("id", "ID", False),
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
                id_col = mapping.get("id")
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
                        # Leading/trailing whitespace is common in ERP CSVs, so clean every field.
                        id_value = (row.get(id_col) or "").strip() if id_col else ""
                        item_id = id_value or None
                        name = (row.get(name_col) or "").strip()
                        if not name:
                            raise ValueError(tr("missing name"))
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
                summary = tr("Imported {count} item(s).").format(count=imported)
                if skipped:
                    summary += " " + tr("Skipped {count} row(s).").format(count=skipped)
                if errors:
                    details = "\n".join(errors[:5])
                    if len(errors) > 5:
                        details += "\n..."
                    QMessageBox.warning(self, tr("Import completed with issues"), summary + "\n\n" + details)
                else:
                    QMessageBox.information(self, tr("Import complete"), summary)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Import error"), str(exc))

    def _apply_translations(self) -> None:
        self.import_button.setText(tr("Import CSV"))

    def _update_action_states(self, *_args) -> None:
        selection_count = len(self.selected_indexes())
        self.edit_button.setEnabled(selection_count == 1)
        self.delete_button.setEnabled(selection_count >= 1)
        # Keep import button accessible regardless of selection.

    def _show_item_error(self, code: str) -> None:
        if code == "duplicate_item_id":
            message = tr("Item ID already exists.")
        elif code == "item_not_found":
            message = tr("Item record could not be found.")
        else:
            message = code
        QMessageBox.warning(self, tr("Validation error"), message)


class OrderView(BaseCrudView):
    """Order list with actions to create, inspect, and delete orders."""

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

        self.edit_button.setVisible(True)

        self.add_button.clicked.connect(self.create_order)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete_order)
        self.refresh_button.clicked.connect(self.refresh)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()

        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _warehouse_name(self, order: Order):
        warehouse = self.db.get_warehouse(order.warehouse_id)
        return warehouse.name if warehouse else tr("Unknown")

    def refresh(self):
        """Reload the order listing, sorted by creation timestamp."""
        self.model.set_rows(self.db.list_orders())
        self.table.resizeColumnsToContents()

    def create_order(self):
        dialog = OrderDialog(self.db, self)
        payload = dialog.get_payload()
        if not payload:
            return
        # ``payload`` always returns a fully-formed Order plus child lines.
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
            tr("Delete order"),
            tr("Delete order #{order_id}?").format(order_id=order.id),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.db.delete_order(order.id)
            self.refresh()

    def edit(self):
        index = self.selected_index()
        if not index:
            return
        order = self.model.get_row(index)
        if not order:
            return
        dialog = OrderDialog(self.db, self, order=order)
        payload = dialog.get_payload()
        if not payload:
            return
        updated_order, lines = payload
        try:
            self.db.update_order_with_lines(updated_order, lines)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, tr("Update error"), str(exc))
            return
        self.refresh()

    def _apply_translations(self) -> None:
        self.add_button.setText(tr("Create order"))
        self.edit_button.setText(tr("View/Edit order"))

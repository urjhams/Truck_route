"""
Concrete CRUD views that compose the dialogs and table utilities.
"""

from __future__ import annotations

import csv
from typing import List, Optional

from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QHeaderView

from TruckRouteApp.logic.db_access import DatabaseService
from TruckRouteApp.models.schema import Customer, Item, Order, Warehouse
from TruckRouteApp.ui.base import BaseCrudView
from TruckRouteApp.ui.dialogs import CSVMappingDialog, CustomerDialog, ItemDialog, WarehouseDialog
from TruckRouteApp.ui.order_dialog import OrderDialog
from TruckRouteApp.ui.table_models import ColumnConfig, SQLModelTableModel


def _open_sniffed_reader(fh) -> csv.DictReader:
    sample = fh.read(2048)
    fh.seek(0)
    try:
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        self.add_button.clicked.connect(self.add)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete)
        self.refresh_button.clicked.connect(self.refresh)
        self.import_button = QPushButton("Import CSV", self)
        self.button_bar.insertWidget(3, self.import_button)
        self.import_button.clicked.connect(self.import_csv)

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
                reader = _open_sniffed_reader(fh)
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

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
                reader = _open_sniffed_reader(fh)
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

        self.add_button.setText("Create order")
        self.edit_button.setText("View/Edit order")
        self.edit_button.setVisible(True)

        self.add_button.clicked.connect(self.create_order)
        self.edit_button.clicked.connect(self.edit)
        self.delete_button.clicked.connect(self.delete_order)
        self.refresh_button.clicked.connect(self.refresh)

        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _warehouse_name(self, order: Order):
        warehouse = self.db.get_warehouse(order.warehouse_id)
        return warehouse.name if warehouse else "Unknown"

    def refresh(self):
        """Reload the order listing, sorted by creation timestamp."""
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
            QMessageBox.critical(self, "Update error", str(exc))
            return
        self.refresh()


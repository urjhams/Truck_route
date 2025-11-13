"""
Standalone dialogs for editing warehouses, customers, and items and mapping CSV imports.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from TruckRouteApp.models.schema import Customer, Item, Warehouse
from TruckRouteApp.ui.i18n import i18n, tr


class CSVMappingDialog(QDialog):
    """
    Lets the user map CSV headers to application fields, enforcing uniqueness and
    allowing optional fields to be skipped.
    """

    def __init__(
        self,
        headers: Sequence[str],
        field_specs: Sequence[Tuple[str, str, bool]],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Map CSV Columns"))
        self.setMinimumWidth(480)
        self._combos: Dict[str, QComboBox] = {}
        self._required: Dict[str, bool] = {}
        self._mapping: Dict[str, Optional[str]] = {}
        self._label_specs: Dict[str, Tuple[QLabel, str, bool]] = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for field, label, required in field_specs:
            combo = QComboBox(self)
            combo.addItem(tr("<Skip>"), "")  # first entry lets users skip optional fields
            for header in headers:
                combo.addItem(header, header)
            combo.setMinimumWidth(260)
            self._combos[field] = combo
            self._required[field] = required
            label_widget = QLabel(self)
            self._label_specs[field] = (label_widget, label, required)
            form.addRow(label_widget, combo)
            # Give each field a sensible default so simple CSVs work with fewer clicks.
            self._auto_select_default(combo, field, label, headers)

        layout.addLayout(form)

        self.note_label = QLabel(self)
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()

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
            # Required fields must not be skipped; optional ones may return None.
            if required and not column:
                QMessageBox.warning(
                    self,
                    tr("Invalid mapping"),
                    tr("Field '{field}' is required.").format(field=field),
                )
                return
            if column:
                # Prevent users from mapping multiple app fields to the same CSV column.
                if column in used_columns:
                    QMessageBox.warning(
                        self,
                        tr("Invalid mapping"),
                        tr("Column '{column}' is assigned multiple times.").format(column=column),
                    )
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

    def _apply_translations(self) -> None:
        self.setWindowTitle(tr("Map CSV Columns"))
        for field, (label_widget, label_text, required) in self._label_specs.items():
            suffix = " *" if required else ""
            label_widget.setText(f"{tr(label_text)}{suffix}")
        self.note_label.setText(tr("Select the CSV column for each field. Fields marked * are required."))
        for combo in self._combos.values():
            combo.setItemText(0, tr("<Skip>"))


class WarehouseDialog(QDialog):
    """Modal editor for creating or updating a single warehouse record."""

    def __init__(self, warehouse: Optional[Warehouse] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Warehouse"))
        self.setMinimumWidth(420)
        self.warehouse = warehouse or Warehouse(name="", lat=0.0, lng=0.0)
        self._labels: list[tuple[QLabel, str]] = []

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
        form.addRow(self._make_label("Name"), self.name_edit)
        form.addRow(self._make_label("Address"), self.address_edit)
        form.addRow(self._make_label("Latitude"), self.lat_edit)
        form.addRow(self._make_label("Longitude"), self.lng_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()

    def get_data(self) -> Optional[Warehouse]:
        """
        Present the dialog until valid numeric coordinates are entered.
        Returns the updated warehouse or None if the dialog was cancelled.
        """
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None
            try:
                # Coerce the coordinate fields before saving them back.
                lat = float(self.lat_edit.text())
                lng = float(self.lng_edit.text())
            except ValueError:
                QMessageBox.warning(
                    self,
                    tr("Validation error"),
                    tr("Latitude and longitude must be numeric."),
                )
                continue

            self.warehouse.name = self.name_edit.text()
            self.warehouse.address = self.address_edit.text()
            self.warehouse.lat = lat
            self.warehouse.lng = lng
            return self.warehouse

    def _make_label(self, key: str) -> QLabel:
        label = QLabel(self)
        self._labels.append((label, key))
        return label

    def _apply_translations(self) -> None:
        self.setWindowTitle(tr("Warehouse"))
        for label, key in self._labels:
            label.setText(tr(key))


class CustomerDialog(QDialog):
    """Modal editor for customer records with optional coordinates."""

    def __init__(self, customer: Optional[Customer] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Customer"))
        self.setMinimumWidth(420)  # widen the dialog for better readability
        self.customer = customer or Customer(name="", lat=0.0, lng=0.0)
        self._original_id = customer.id if customer else None
        self._labels: List[tuple[QLabel, str]] = []

        form = QFormLayout(self)
        self.id_edit = QLineEdit("" if self.customer.id is None else str(self.customer.id), self)
        self.id_edit.setMinimumWidth(200)
        self.id_edit.setPlaceholderText(tr("Auto-generated when empty"))
        form.addRow(self._make_label("ID"), self.id_edit)

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
        form.addRow(self._make_label("Name"), self.name_edit)
        form.addRow(self._make_label("Address"), self.address_edit)
        form.addRow(self._make_label("Latitude"), self.lat_edit)
        form.addRow(self._make_label("Longitude"), self.lng_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()

    def get_data(self) -> Optional[tuple[Customer, Optional[str]]]:
        """
        Display the dialog until the submitted latitude/longitude values are valid.
        Returns the updated customer and its original ID (if any), or None when cancelled.
        """
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None
            lat_text = self.lat_edit.text().strip()
            lng_text = self.lng_edit.text().strip()
            try:
                # Allow blank coordinate cells by treating them as ``None``.
                lat = float(lat_text) if lat_text else None
            except ValueError:
                QMessageBox.warning(
                    self,
                    tr("Validation error"),
                    tr("Latitude must be a numeric value."),
                )
                continue
            try:
                lng = float(lng_text) if lng_text else None
            except ValueError:
                QMessageBox.warning(
                    self,
                    tr("Validation error"),
                    tr("Longitude must be a numeric value."),
                )
                continue
            id_text = self.id_edit.text().strip()
            self.customer.id = id_text or None
            self.customer.name = self.name_edit.text()
            self.customer.address = self.address_edit.text()
            self.customer.lat = lat
            self.customer.lng = lng
            return self.customer, self._original_id

    def _make_label(self, key: str) -> QLabel:
        label = QLabel(self)
        self._labels.append((label, key))
        return label

    def _apply_translations(self) -> None:
        self.setWindowTitle(tr("Customer"))
        placeholder = tr("Auto-generated when empty")
        self.id_edit.setPlaceholderText(placeholder)
        for label, key in self._labels:
            label.setText(tr(key))


class ItemDialog(QDialog):
    """Modal editor for product items with optional packaging and pricing metadata."""

    def __init__(self, item: Optional[Item] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Item"))
        self.setMinimumWidth(460)
        self.item = item or Item(name="")
        self._original_id = item.id if item else None
        self._labels: List[tuple[QLabel, str]] = []

        form = QFormLayout(self)
        self.id_edit = QLineEdit("" if self.item.id is None else str(self.item.id), self)
        self.id_edit.setMinimumWidth(160)
        self.id_edit.setPlaceholderText(tr("Auto-generated when empty"))
        form.addRow(self._make_label("ID"), self.id_edit)

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
        form.addRow(self._make_label("Name"), self.name_edit)
        form.addRow(self._make_label("KTN per Pal"), self.ktn_per_pal_edit)
        form.addRow(self._make_label("Items per KTN"), self.items_per_ktn_edit)
        form.addRow(self._make_label("Price (gross)"), self.price_gross_edit)
        form.addRow(self._make_label("Price (net)"), self.price_net_edit)
        form.addRow(self._make_label("Tax"), self.tax_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        i18n.language_changed.connect(self._apply_translations)
        self._apply_translations()

    def get_data(self) -> Optional[tuple[Item, Optional[str]]]:
        """
        Persist user edits after validating numeric fields.
        Returns the updated item plus its original ID (if any) or None if the dialog was cancelled.
        """
        while True:
            if self.exec() != QDialog.DialogCode.Accepted:
                return None

            id_text = self.id_edit.text().strip() or None

            try:
                # Most spreadsheets store integers as floats, hence ``int(float(...))``.
                ktn_per_pal = int(self.ktn_per_pal_edit.text()) if self.ktn_per_pal_edit.text().strip() else None
            except ValueError:
                QMessageBox.warning(
                    self,
                    tr("Validation error"),
                    tr("KTN per Pal must be an integer."),
                )
                continue

            items_per_ktn_text = self.items_per_ktn_edit.text().strip()
            items_per_ktn = items_per_ktn_text if items_per_ktn_text else None

            try:
                price_gross = float(self.price_gross_edit.text()) if self.price_gross_edit.text().strip() else None
            except ValueError:
                QMessageBox.warning(
                    self,
                    tr("Validation error"),
                    tr("Price (gross) must be numeric."),
                )
                continue

            try:
                price_net = float(self.price_net_edit.text()) if self.price_net_edit.text().strip() else None
            except ValueError:
                QMessageBox.warning(
                    self,
                    tr("Validation error"),
                    tr("Price (net) must be numeric."),
                )
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
            return self.item, self._original_id

    def _make_label(self, key: str) -> QLabel:
        label = QLabel(self)
        self._labels.append((label, key))
        return label

    def _apply_translations(self) -> None:
        self.setWindowTitle(tr("Item"))
        self.id_edit.setPlaceholderText(tr("Auto-generated when empty"))
        for label, key in self._labels:
            label.setText(tr(key))

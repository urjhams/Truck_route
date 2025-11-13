"""
Lightweight internationalisation helper used by the Qt widgets.
"""

from __future__ import annotations

from typing import Dict, Mapping

from PySide6.QtCore import QObject, Signal


LANGUAGE_OPTIONS = [
    ("en", "English"),
    ("de", "German"),
    ("vi", "Vietnamese"),
    ("zh", "Mandarin Chinese"),
]


# Base translation catalog (English/German). Additional languages are merged later.
BASE_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "Add": {"en": "Add", "de": "Hinzufügen"},
    "Edit": {"en": "Edit", "de": "Bearbeiten"},
    "Delete": {"en": "Delete", "de": "Löschen"},
    "Refresh": {"en": "Refresh", "de": "Aktualisieren"},
    "Error": {"en": "Error", "de": "Fehler"},
    "Unable to open editor: {details}": {
        "en": "Unable to open editor: {details}",
        "de": "Editor kann nicht geöffnet werden: {details}",
    },
    "Truck Route Planner": {"en": "Truck Route Planner", "de": "Lkw-Routenplaner"},
    "Warehouses": {"en": "Warehouses", "de": "Lager"},
    "Customers": {"en": "Customers", "de": "Kunden"},
    "Items": {"en": "Items", "de": "Artikel"},
    "Orders": {"en": "Orders", "de": "Aufträge"},
    "Created": {"en": "Created", "de": "Erstellt"},
    "Order": {"en": "Order", "de": "Auftrag"},
    "Export database": {"en": "Export database", "de": "Datenbank exportieren"},
    "Import database": {"en": "Import database", "de": "Datenbank importieren"},
    "Export failed": {"en": "Export failed", "de": "Export fehlgeschlagen"},
    "Import failed": {"en": "Import failed", "de": "Import fehlgeschlagen"},
    "Export complete": {"en": "Export complete", "de": "Export abgeschlossen"},
    "Import complete": {"en": "Import complete", "de": "Import abgeschlossen"},
    "Language": {"en": "Language", "de": "Sprache"},
    "English": {"en": "English", "de": "Englisch"},
    "German": {"en": "German", "de": "Deutsch"},
    "Vietnamese": {"en": "Vietnamese", "de": "Vietnamesisch"},
    "Mandarin Chinese": {"en": "Mandarin Chinese", "de": "Mandarin"},
    "Import error": {"en": "Import error", "de": "Importfehler"},
    "Import CSV": {"en": "Import CSV", "de": "CSV importieren"},
    "Map CSV Columns": {"en": "Map CSV Columns", "de": "CSV-Spalten zuordnen"},
    "<Skip>": {"en": "<Skip>", "de": "<Überspringen>"},
    "Auto-generated when empty": {
        "en": "Auto-generated when empty",
        "de": "Automatisch, wenn leer",
    },
    "Select the CSV column for each field. Fields marked * are required.": {
        "en": "Select the CSV column for each field. Fields marked * are required.",
        "de": "Wählen Sie für jedes Feld eine CSV-Spalte. Felder mit * sind erforderlich.",
    },
    "Invalid mapping": {"en": "Invalid mapping", "de": "Ungültige Zuordnung"},
    "Field '{field}' is required.": {
        "en": "Field '{field}' is required.",
        "de": "Feld '{field}' ist erforderlich.",
    },
    "Column '{column}' is assigned multiple times.": {
        "en": "Column '{column}' is assigned multiple times.",
        "de": "Spalte '{column}' wurde mehrfach zugewiesen.",
    },
    "Customer ID already exists.": {
        "en": "Customer ID already exists.",
        "de": "Kunden-ID ist bereits vorhanden.",
    },
    "Customer record could not be found.": {
        "en": "Customer record could not be found.",
        "de": "Kundendatensatz wurde nicht gefunden.",
    },
    "Item ID already exists.": {
        "en": "Item ID already exists.",
        "de": "Artikel-ID ist bereits vorhanden.",
    },
    "Item record could not be found.": {
        "en": "Item record could not be found.",
        "de": "Artikeldatensatz wurde nicht gefunden.",
    },
    "Import customers from CSV": {
        "en": "Import customers from CSV",
        "de": "Kunden aus CSV importieren",
    },
    "Import items from CSV": {
        "en": "Import items from CSV",
        "de": "Artikel aus CSV importieren",
    },
    "CSV files (*.csv);;All files (*)": {
        "en": "CSV files (*.csv);;All files (*)",
        "de": "CSV-Dateien (*.csv);;Alle Dateien (*)",
    },
    "CSV file must include a header row.": {
        "en": "CSV file must include a header row.",
        "de": "Die CSV-Datei muss eine Kopfzeile enthalten.",
    },
    "missing id": {"en": "missing id", "de": "ID fehlt"},
    "missing name": {"en": "missing name", "de": "Name fehlt"},
    "Delete warehouse": {"en": "Delete warehouse", "de": "Lager löschen"},
    "Delete warehouse '{name}'?": {
        "en": "Delete warehouse '{name}'?",
        "de": "Lager '{name}' löschen?",
    },
    "Delete customer": {"en": "Delete customer", "de": "Kunde löschen"},
    "Delete customer '{name}'?": {
        "en": "Delete customer '{name}'?",
        "de": "Kunden '{name}' löschen?",
    },
    "Delete item": {"en": "Delete item", "de": "Artikel löschen"},
    "Delete item '{name}'?": {
        "en": "Delete item '{name}'?",
        "de": "Artikel '{name}' löschen?",
    },
    "Delete order": {"en": "Delete order", "de": "Auftrag löschen"},
    "Delete order #{order_id}?": {
        "en": "Delete order #{order_id}?",
        "de": "Auftrag Nr. {order_id} löschen?",
    },
    "Update error": {"en": "Update error", "de": "Aktualisierungsfehler"},
    "Create order": {"en": "Create order", "de": "Auftrag anlegen"},
    "View/Edit order": {"en": "View/Edit order", "de": "Auftrag anzeigen/bearbeiten"},
    "Unknown": {"en": "Unknown", "de": "Unbekannt"},
    "KTN per Pal": {"en": "KTN per Pal", "de": "KTN pro Palette"},
    "KTN/pal": {"en": "KTN/pal", "de": "KTN/Pal"},
    "Items per KTN": {"en": "Items per KTN", "de": "Artikel pro KTN"},
    "Items/KTN": {"en": "Items/KTN", "de": "Artikel/KTN"},
    "Price (gross)": {"en": "Price (gross)", "de": "Preis (brutto)"},
    "Price (net)": {"en": "Price (net)", "de": "Preis (netto)"},
    "Tax": {"en": "Tax", "de": "Steuer"},
    "KTN per Pal must be an integer.": {
        "en": "KTN per Pal must be an integer.",
        "de": "KTN pro Palette muss eine ganze Zahl sein.",
    },
    "Price (gross) must be numeric.": {
        "en": "Price (gross) must be numeric.",
        "de": "Der Bruttopreis muss numerisch sein.",
    },
    "Price (net) must be numeric.": {
        "en": "Price (net) must be numeric.",
        "de": "Der Nettopreis muss numerisch sein.",
    },
    "Imported {count} item(s).": {
        "en": "Imported {count} item(s).",
        "de": "{count} Artikel importiert.",
    },
    "Skipped {count} row(s).": {
        "en": "Skipped {count} row(s).",
        "de": "{count} Zeile(n) übersprungen.",
    },
    "Import completed with issues": {
        "en": "Import completed with issues",
        "de": "Import mit Problemen abgeschlossen",
    },
}

BASE_TRANSLATIONS.update(
    {
        "Warehouse": {"en": "Warehouse", "de": "Lager"},
        "Customer": {"en": "Customer", "de": "Kunde"},
        "Item": {"en": "Item", "de": "Artikel"},
        "Name": {"en": "Name", "de": "Name"},
        "Address": {"en": "Address", "de": "Adresse"},
        "Latitude": {"en": "Latitude", "de": "Breitengrad"},
        "Longitude": {"en": "Longitude", "de": "Längengrad"},
        "ID": {"en": "ID", "de": "ID"},
        "Required": {"en": "Required", "de": "Erforderlich"},
        "Latitude must be a numeric value.": {
            "en": "Latitude must be a numeric value.",
            "de": "Der Breitengrad muss numerisch sein.",
        },
        "Longitude must be a numeric value.": {
            "en": "Longitude must be a numeric value.",
            "de": "Der Längengrad muss numerisch sein.",
        },
        "ID is required.": {"en": "ID is required.", "de": "ID ist erforderlich."},
        "Validation error": {"en": "Validation error", "de": "Validierungsfehler"},
        "Latitude and longitude must be numeric.": {
            "en": "Latitude and longitude must be numeric.",
            "de": "Breiten- und Längengrad müssen numerisch sein.",
        },
        "Add Line": {"en": "Add Line", "de": "Position hinzufügen"},
        "Products": {"en": "Products", "de": "Produkte"},
        "Name": {"en": "Name", "de": "Name"},
        "Pallets": {"en": "Pallets", "de": "Paletten"},
        "Karton/Pal": {"en": "Karton/Pal", "de": "Karton/Pal"},
        "Number of pallets": {"en": "Number of pallets", "de": "Anzahl Paletten"},
        "Karton per pallet": {"en": "Karton per pallet", "de": "Karton pro Palette"},
        "Add at least one product.": {
            "en": "Add at least one product.",
            "de": "Fügen Sie mindestens ein Produkt hinzu.",
        },
        "Row {idx}: pallet count is required.": {
            "en": "Row {idx}: pallet count is required.",
            "de": "Zeile {idx}: Palettenmenge ist erforderlich.",
        },
        "Row {idx}: pallet count must be greater than zero.": {
            "en": "Row {idx}: pallet count must be greater than zero.",
            "de": "Zeile {idx}: Palettenmenge muss größer als null sein.",
        },
        "Row {idx}: karton per pallet is required.": {
            "en": "Row {idx}: karton per pallet is required.",
            "de": "Zeile {idx}: Karton pro Palette ist erforderlich.",
        },
        "Add line": {"en": "Add line", "de": "Position hinzufügen"},
        "Remove line": {"en": "Remove line", "de": "Position entfernen"},
        "Estimate route": {"en": "Estimate route", "de": "Route berechnen"},
        "Export to Excel": {"en": "Export to Excel", "de": "In Excel exportieren"},
        "Export to DOCX": {"en": "Export to DOCX", "de": "In DOCX exportieren"},
        "Route preview": {"en": "Route preview", "de": "Routenvorschau"},
        "Remove": {"en": "Remove", "de": "Entfernen"},
        "Missing references": {"en": "Missing references", "de": "Fehlende Referenzen"},
        "Some order lines reference customers or items that no longer exist and were skipped.": {
            "en": "Some order lines reference customers or items that no longer exist and were skipped.",
            "de": "Einige Auftragspositionen verweisen auf nicht mehr vorhandene Kunden oder Artikel und wurden übersprungen.",
        },
        "Missing data": {"en": "Missing data", "de": "Fehlende Daten"},
        "Define at least one customer and one item first.": {
            "en": "Define at least one customer and one item first.",
            "de": "Legen Sie zunächst mindestens einen Kunden und einen Artikel an.",
        },
        "Invalid value": {"en": "Invalid value", "de": "Ungültiger Wert"},
        "Pallet count must be a number.": {
            "en": "Pallet count must be a number.",
            "de": "Die Palettenmenge muss numerisch sein.",
        },
        "Pallet count must be greater than zero.": {
            "en": "Pallet count must be greater than zero.",
            "de": "Die Palettenmenge muss größer als null sein.",
        },
        "Karton per pallet must be a number.": {
            "en": "Karton per pallet must be a number.",
            "de": "Karton pro Palette muss eine Zahl sein.",
        },
        "Karton per pallet must be greater than zero.": {
            "en": "Karton per pallet must be greater than zero.",
            "de": "Karton pro Palette muss größer als null sein.",
        },
        "Missing lines": {"en": "Missing lines", "de": "Fehlende Positionen"},
        "Please add at least one order line.": {
            "en": "Please add at least one order line.",
            "de": "Bitte fügen Sie mindestens eine Auftragsposition hinzu.",
        },
        "Add at least one order line.": {
            "en": "Add at least one order line.",
            "de": "Fügen Sie mindestens eine Auftragsposition hinzu.",
        },
        "Add at least one order line before exporting.": {
            "en": "Add at least one order line before exporting.",
            "de": "Fügen Sie vor dem Export mindestens eine Auftragsposition hinzu.",
        },
        "Customer '{customer_name}' is missing latitude/longitude. Please update the customer before routing.": {
            "en": "Customer '{customer_name}' is missing latitude/longitude. Please update the customer before routing.",
            "de": "Beim Kunden '{customer_name}' fehlen Breiten- und Längengrad. Bitte aktualisieren Sie den Kunden vor der Routenberechnung.",
        },
        "Route calculation": {"en": "Route calculation", "de": "Routenberechnung"},
        "A route calculation is already in progress.": {
            "en": "A route calculation is already in progress.",
            "de": "Eine Routenberechnung läuft bereits.",
        },
        "Calculating route...": {"en": "Calculating route...", "de": "Route wird berechnet ..."},
        "Route calculation failed.": {"en": "Route calculation failed.", "de": "Routenberechnung fehlgeschlagen."},
        "Routing error": {"en": "Routing error", "de": "Routing-Fehler"},
        "Unable to compute route.": {"en": "Unable to compute route.", "de": "Route kann nicht berechnet werden."},
        "Route ready — total distance ≈ {km:.2f} km": {
            "en": "Route ready — total distance ≈ {km:.2f} km",
            "de": "Route bereit – Gesamtdistanz ≈ {km:.2f} km",
        },
        "{stop_name} (Depot)": {"en": "{stop_name} (Depot)", "de": "{stop_name} (Depot)"},
        "Missing route": {"en": "Missing route", "de": "Route fehlt"},
        "Estimate the route before exporting.": {
            "en": "Estimate the route before exporting.",
            "de": "Berechnen Sie die Route vor dem Export.",
        },
        "Export route to Excel": {"en": "Export route to Excel", "de": "Route nach Excel exportieren"},
        "Excel files (*.xlsx);;All files (*)": {
            "en": "Excel files (*.xlsx);;All files (*)",
            "de": "Excel-Dateien (*.xlsx);;Alle Dateien (*)",
        },
        "Missing warehouse": {"en": "Missing warehouse", "de": "Lager fehlt"},
        "Select a warehouse before exporting.": {
            "en": "Select a warehouse before exporting.",
            "de": "Wählen Sie vor dem Export ein Lager aus.",
        },
        "Select a warehouse.": {"en": "Select a warehouse.", "de": "Wählen Sie ein Lager aus."},
        "No route stops": {"en": "No route stops", "de": "Keine Routenstopps"},
        "Add lines and estimate the route before exporting.": {
            "en": "Add lines and estimate the route before exporting.",
            "de": "Fügen Sie Positionen hinzu und berechnen Sie die Route vor dem Export.",
        },
        "Excel file saved to {path}": {
            "en": "Excel file saved to {path}",
            "de": "Excel-Datei gespeichert unter {path}",
        },
        "Export pallets to DOCX": {"en": "Export pallets to DOCX", "de": "Paletten nach DOCX exportieren"},
        "Word files (*.docx);;All files (*)": {
            "en": "Word files (*.docx);;All files (*)",
            "de": "Word-Dateien (*.docx);;Alle Dateien (*)",
        },
        "Invalid pallet count": {"en": "Invalid pallet count", "de": "Ungültige Palettenmenge"},
        "No pallets": {"en": "No pallets", "de": "Keine Paletten"},
        "Nothing to export — please enter pallet quantities.": {
            "en": "Nothing to export — please enter pallet quantities.",
            "de": "Nichts zu exportieren – bitte Palettenmengen eingeben.",
        },
        "DOCX file saved to {path}": {
            "en": "DOCX file saved to {path}",
            "de": "DOCX-Datei gespeichert unter {path}",
        },
        "SQLite database (*.db);;All files (*)": {
            "en": "SQLite database (*.db);;All files (*)",
            "de": "SQLite-Datenbanken (*.db);;Alle Dateien (*)",
        },
        "Database exported to:\n{destination}": {
            "en": "Database exported to:\n{destination}",
            "de": "Datenbank exportiert nach:\n{destination}",
        },
        "Importing will overwrite the current data. Continue?": {
            "en": "Importing will overwrite the current data. Continue?",
            "de": "Beim Import werden die aktuellen Daten überschrieben. Fortfahren?",
        },
        "Database replaced with:\n{destination}": {
            "en": "Database replaced with:\n{destination}",
            "de": "Datenbank ersetzt durch:\n{destination}",
        },
        "{customer} / {item}: pallet count must be positive.": {
            "en": "{customer} / {item}: pallet count must be positive.",
            "de": "{customer} / {item}: Palettenmenge muss positiv sein.",
        },
        "{customer} / {item}: pallet count must be a whole number for DOCX export.": {
            "en": "{customer} / {item}: pallet count must be a whole number for DOCX export.",
            "de": "{customer} / {item}: Palettenmenge muss für den DOCX-Export eine ganze Zahl sein.",
        },
    }
)

VI_TRANSLATIONS = {
    "Add": "Thêm",
    "Edit": "Chỉnh sửa",
    "Delete": "Xóa",
    "Refresh": "Làm mới",
    "Error": "Lỗi",
    "Unable to open editor: {details}": "Không thể mở trình chỉnh sửa: {details}",
    "Truck Route Planner": "Trình lập kế hoạch tuyến xe tải",
    "Warehouses": "Kho hàng",
    "Customers": "Khách hàng",
    "Items": "Sản phẩm",
    "Orders": "Đơn hàng",
    "Created": "Đã tạo",
    "Order": "Đơn hàng",
    "Export database": "Xuất cơ sở dữ liệu",
    "Import database": "Nhập cơ sở dữ liệu",
    "Export failed": "Xuất thất bại",
    "Import failed": "Nhập thất bại",
    "Export complete": "Xuất hoàn tất",
    "Import complete": "Nhập hoàn tất",
    "Language": "Ngôn ngữ",
    "English": "Tiếng Anh",
    "German": "Tiếng Đức",
    "Vietnamese": "Tiếng Việt",
    "Mandarin Chinese": "Tiếng Trung (Phổ thông)",
    "Import error": "Lỗi nhập",
    "Import CSV": "Nhập CSV",
    "Map CSV Columns": "Ánh xạ cột CSV",
    "<Skip>": "<Bỏ qua>",
    "Auto-generated when empty": "Tạo tự động khi để trống",
    "Select the CSV column for each field. Fields marked * are required.": "Chọn cột CSV cho từng trường. Các trường đánh dấu * là bắt buộc.",
    "Invalid mapping": "Ánh xạ không hợp lệ",
    "Field '{field}' is required.": "Trường '{field}' là bắt buộc.",
    "Column '{column}' is assigned multiple times.": "Cột '{column}' được gán nhiều lần.",
    "Customer ID already exists.": "ID khách hàng đã tồn tại.",
    "Customer record could not be found.": "Không tìm thấy bản ghi khách hàng.",
    "Item ID already exists.": "ID sản phẩm đã tồn tại.",
    "Item record could not be found.": "Không tìm thấy bản ghi sản phẩm.",
    "Import customers from CSV": "Nhập khách hàng từ CSV",
    "Import items from CSV": "Nhập sản phẩm từ CSV",
    "CSV files (*.csv);;All files (*)": "Tệp CSV (*.csv);;Tất cả tệp (*)",
    "CSV file must include a header row.": "Tệp CSV phải có dòng tiêu đề.",
    "missing id": "thiếu ID",
    "missing name": "thiếu tên",
    "Delete warehouse": "Xóa kho",
    "Delete warehouse '{name}'?": "Xóa kho '{name}'?",
    "Delete customer": "Xóa khách hàng",
    "Delete customer '{name}'?": "Xóa khách hàng '{name}'?",
    "Delete item": "Xóa sản phẩm",
    "Delete item '{name}'?": "Xóa sản phẩm '{name}'?",
    "Delete order": "Xóa đơn hàng",
    "Delete order #{order_id}?": "Xóa đơn hàng #{order_id}?",
    "Update error": "Lỗi cập nhật",
    "Create order": "Tạo đơn hàng",
    "View/Edit order": "Xem/Chỉnh sửa đơn hàng",
    "Unknown": "Không xác định",
}

ZH_TRANSLATIONS = {
    "Add": "新增",
    "Edit": "编辑",
    "Delete": "删除",
    "Refresh": "刷新",
    "Error": "错误",
    "Unable to open editor: {details}": "无法打开编辑器：{details}",
    "Truck Route Planner": "卡车路线规划器",
    "Warehouses": "仓库",
    "Customers": "客户",
    "Items": "商品",
    "Orders": "订单",
    "Created": "创建时间",
    "Order": "订单",
    "Export database": "导出数据库",
    "Import database": "导入数据库",
    "Export failed": "导出失败",
    "Import failed": "导入失败",
    "Export complete": "导出完成",
    "Import complete": "导入完成",
    "Language": "语言",
    "English": "英语",
    "German": "德语",
    "Vietnamese": "越南语",
    "Mandarin Chinese": "中文（普通话）",
    "Import error": "导入错误",
    "Import CSV": "导入 CSV",
    "Map CSV Columns": "映射 CSV 列",
    "<Skip>": "<跳过>",
    "Auto-generated when empty": "留空则自动生成",
    "Select the CSV column for each field. Fields marked * are required.": "为每个字段选择 CSV 列。带 * 的字段为必填项。",
    "Invalid mapping": "映射无效",
    "Field '{field}' is required.": "字段“{field}”为必填项。",
    "Column '{column}' is assigned multiple times.": "列“{column}”被重复分配。",
    "Customer ID already exists.": "客户 ID 已存在。",
    "Customer record could not be found.": "找不到客户记录。",
    "Item ID already exists.": "商品 ID 已存在。",
    "Item record could not be found.": "找不到商品记录。",
    "Import customers from CSV": "从 CSV 导入客户",
    "Import items from CSV": "从 CSV 导入商品",
    "CSV files (*.csv);;All files (*)": "CSV 文件 (*.csv);;所有文件 (*)",
    "CSV file must include a header row.": "CSV 文件必须包含表头行。",
    "missing id": "缺少 ID",
    "missing name": "缺少名称",
    "Delete warehouse": "删除仓库",
    "Delete warehouse '{name}'?": "删除仓库“{name}”？",
    "Delete customer": "删除客户",
    "Delete customer '{name}'?": "删除客户“{name}”？",
    "Delete item": "删除商品",
    "Delete item '{name}'?": "删除商品“{name}”？",
    "Delete order": "删除订单",
    "Delete order #{order_id}?": "删除订单 #{order_id}？",
    "Update error": "更新错误",
    "Create order": "创建订单",
    "View/Edit order": "查看/编辑订单",
    "Unknown": "未知",
}


SUPPORTED_LANG_CODES = [code for code, _label in LANGUAGE_OPTIONS]


def _build_translation_catalog() -> Dict[str, Dict[str, str]]:
    catalog: Dict[str, Dict[str, str]] = {key: dict(value) for key, value in BASE_TRANSLATIONS.items()}

    def merge(lang_code: str, translations: Dict[str, str]) -> None:
        for key, text in translations.items():
            catalog.setdefault(key, {})
            catalog[key][lang_code] = text

    merge("vi", VI_TRANSLATIONS)
    merge("zh", ZH_TRANSLATIONS)

    for entry in catalog.values():
        fallback = entry.get("en") or next(iter(entry.values()))
        for code in SUPPORTED_LANG_CODES:
            entry.setdefault(code, fallback)
    return catalog


TRANSLATIONS = _build_translation_catalog()


class LanguageManager(QObject):
    """Singleton-style helper managing the current UI language and notifications."""

    language_changed = Signal(str)

    def __init__(self, translations: Mapping[str, Mapping[str, str]], default_language: str = "en"):
        super().__init__()
        self._translations = translations
        self._language = default_language

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        """Switch to a new language and notify listeners."""
        supported = {code for code, _ in LANGUAGE_OPTIONS}
        if language not in supported:
            raise ValueError(f"Unsupported language '{language}'")
        if language == self._language:
            return
        self._language = language
        self.language_changed.emit(language)

    def translate(self, text: str, language: str | None = None) -> str:
        """Return the translated string for the active or provided language."""
        lang = language or self._language
        entry = self._translations.get(text)
        if not entry:
            return text
        if lang in entry:
            return entry[lang]
        if "en" in entry:
            return entry["en"]
        # Fall back to any available translation in the catalog.
        return next(iter(entry.values()))


i18n = LanguageManager(TRANSLATIONS)


def tr(text: str) -> str:
    """Convenience wrapper mirroring Qt's translate helpers."""
    return i18n.translate(text)

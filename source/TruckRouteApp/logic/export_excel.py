"""
Utility helpers for exporting the computed route into an Excel workbook.

The format mimics the sample workbook under ``test/`` where each customer
occupies one block consisting of two logical columns:

- Column group B–G: textual summary of ordered items per customer.
- Column H: customer name followed by the address split across multiple lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.xlsx"

_COLUMN_ITEM_START = 2  # Column B
_COLUMN_SECONDARY = 8  # Column H
_TOP_PADDING_ROWS = 4
_COLUMN_WIDTHS = {
    2: 6,   # pallets value
    3: 6,   # "Pal."
    4: 4,   # "x"
    5: 28,  # item name
    6: 6,   # ktn qty
    7: 6,   # "ktn"
    8: 32,  # customer / address block
}
_DATA_START_ROW = _TOP_PADDING_ROWS + 1
_CLEAR_ROW_COUNT = 400  # generous default to wipe prior runs without touching images

_THIN_SIDE = Side(style="thin", color="000000")
_THIN_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)


def _can_edit_cell(cell, merged_ranges) -> bool:
    for merged in merged_ranges:
        if cell.coordinate in merged:
            return cell.row == merged.min_row and cell.column == merged.min_col
    return True


@dataclass(slots=True)
class RouteExcelItem:
    """Single product line destined for a customer in the export."""

    item_name: str
    pallets: float
    cartons_per_pallet: Optional[float] = None


@dataclass(slots=True)
class RouteExcelRow:
    """
    Representation of one stop within the exported workbook.

    Rows should be supplied in route order (first destination after the depot
    through the final destination). The exporter takes care of reversing the
    order so that the first destination appears at the bottom of the sheet.
    """

    customer_name: str
    address: Optional[str]
    items: Sequence[RouteExcelItem] = field(default_factory=tuple)
    customer_id: Optional[str] = None

    @property
    def total_pallets(self) -> float:
        return float(sum(item.pallets for item in self.items))


def _load_workbook_from_template(path: Path) -> Tuple[Workbook, Worksheet]:
    if path.exists():
        workbook = load_workbook(path)
    else:
        workbook = Workbook()
    worksheet = workbook.active
    if worksheet is None:
        worksheet = workbook.create_sheet("Route")
    else:
        worksheet.title = "Route"
    for idx, width in _COLUMN_WIDTHS.items():
        worksheet.column_dimensions[get_column_letter(idx)].width = width
    _clear_data_region(worksheet)
    return workbook, worksheet


def _clear_data_region(worksheet: Worksheet) -> None:
    max_row = max(_DATA_START_ROW + _CLEAR_ROW_COUNT, worksheet.max_row or _DATA_START_ROW)
    merged = list(worksheet.merged_cells.ranges)
    for row in worksheet.iter_rows(
        min_row=_DATA_START_ROW,
        max_row=max_row,
        min_col=_COLUMN_ITEM_START,
        max_col=_COLUMN_SECONDARY,
    ):
        for cell in row:
            if _can_edit_cell(cell, merged):
                cell.value = None
                cell.border = Border()


def _apply_grid_border(
    worksheet: Worksheet,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> None:
    """
    Draw a cleaner table border:
    - Outer border around the whole table region
    - Vertical borders only at: end of items section, and end of address column
    - Horizontal border only under final item of each customer block (caller passes correct max_row)
    """

    # Outer rectangle around the table
    for col in range(min_col, max_col + 1):
        top = worksheet.cell(row=min_row, column=col)
        bottom = worksheet.cell(row=max_row, column=col)
        top.border = Border(top=_THIN_SIDE, left=top.border.left, right=top.border.right, bottom=top.border.bottom)
        bottom.border = Border(bottom=_THIN_SIDE, left=bottom.border.left, right=bottom.border.right, top=bottom.border.top)

    for row in range(min_row, max_row + 1):
        left = worksheet.cell(row=row, column=min_col)
        right = worksheet.cell(row=row, column=max_col)
        left.border = Border(left=_THIN_SIDE, top=left.border.top, right=left.border.right, bottom=left.border.bottom)
        right.border = Border(right=_THIN_SIDE, top=right.border.top, left=right.border.left, bottom=right.border.bottom)

    # Vertical border after items column group (ktn col)
    divider_col = _COLUMN_ITEM_START + 5
    for row in range(min_row, max_row + 1):
        cell = worksheet.cell(row=row, column=divider_col)
        cell.border = Border(
            right=_THIN_SIDE,
            left=cell.border.left,
            top=cell.border.top,
            bottom=cell.border.bottom,
        )

    # Vertical border after address column
    for row in range(min_row, max_row + 1):
        cell = worksheet.cell(row=row, column=_COLUMN_SECONDARY)
        cell.border = Border(
            right=_THIN_SIDE,
            left=cell.border.left,
            top=cell.border.top,
            bottom=cell.border.bottom,
        )

    # Horizontal separator under full customer block (final row)
    for col in range(min_col, max_col + 1):
        cell = worksheet.cell(row=max_row, column=col)
        cell.border = Border(
            bottom=_THIN_SIDE,
            top=cell.border.top,
            left=cell.border.left,
            right=cell.border.right,
        )


def _normalized_number(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 3)


def _split_address_lines(address: Optional[str]) -> list[str]:
    if not address:
        return []
    raw = address.strip()
    if not raw:
        return []
    if "," not in raw:
        return [raw]
    first, remainder = raw.split(",", 1)
    lines = [first.strip()]
    remainder = remainder.strip()
    if remainder:
        lines.append(remainder)
    return lines


def _write_item_line(worksheet: Worksheet, row_idx: int, item: RouteExcelItem) -> None:
    pallets_value = _normalized_number(item.pallets)
    cartons_value = _normalized_number(item.cartons_per_pallet)
    worksheet.cell(row=row_idx, column=_COLUMN_ITEM_START, value=pallets_value)
    worksheet.cell(row=row_idx, column=_COLUMN_ITEM_START + 1, value="Pal.")
    worksheet.cell(row=row_idx, column=_COLUMN_ITEM_START + 2, value="x")
    worksheet.cell(row=row_idx, column=_COLUMN_ITEM_START + 3, value=item.item_name)
    worksheet.cell(row=row_idx, column=_COLUMN_ITEM_START + 4, value=cartons_value)
    worksheet.cell(
        row=row_idx,
        column=_COLUMN_ITEM_START + 5,
        value="ktn" if cartons_value is not None else None,
    )


def _write_customer_block(worksheet: Worksheet, start_row: int, row: RouteExcelRow) -> int:
    worksheet.cell(row=start_row, column=_COLUMN_SECONDARY, value=row.customer_name)
    current_row = start_row + 1
    address_lines = _split_address_lines(row.address)
    line_count = max(len(row.items), len(address_lines))
    if line_count == 0:
        line_count = 1  # keep spacing even when no items/address

    for offset in range(line_count):
        if offset < len(row.items):
            _write_item_line(worksheet, current_row, row.items[offset])
        if offset < len(address_lines):
            worksheet.cell(row=current_row, column=_COLUMN_SECONDARY, value=address_lines[offset])
        current_row += 1

    worksheet.cell(row=current_row, column=_COLUMN_SECONDARY, value=None)  # blank spacer row
    return current_row + 1


def export_route_to_excel(
    output_path: Path,
    rows: Sequence[RouteExcelRow],
    *,
    order_date: Optional[datetime | date | str] = None,
    total_pallets: Optional[float] = None,
    template_path: Optional[Path] = None,
) -> Path:
    """
    Export the provided rows to an Excel file matching the sample layout.
    """

    template = template_path or DEFAULT_TEMPLATE
    workbook, worksheet = _load_workbook_from_template(template)

    current_row = _DATA_START_ROW
    table_start_row = current_row
    table_end_row = current_row - 1
    for row in reversed(rows):
        current_row = _write_customer_block(worksheet, current_row, row)
        table_end_row = max(table_end_row, current_row - 2)  # last row containing data

    current_row += 1  # extra blank row before summary

    summary_start_row = current_row
    if order_date:
        if isinstance(order_date, datetime):
            date_value: str | datetime | date = order_date.strftime("%d.%m.%Y")
        elif isinstance(order_date, date):
            date_value = order_date.strftime("%d.%m.%Y")
        else:
            date_value = order_date
        worksheet.cell(row=current_row, column=_COLUMN_ITEM_START, value=date_value)
        current_row += 1

    total = _normalized_number(total_pallets) if total_pallets is not None else None
    if total is None:
        total = _normalized_number(sum(row.total_pallets for row in rows))
    worksheet.cell(row=current_row, column=_COLUMN_ITEM_START, value=total)
    worksheet.cell(row=current_row, column=_COLUMN_ITEM_START + 1, value="Pal.")
    summary_end_row = current_row

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if table_end_row >= table_start_row and rows:
        _apply_grid_border(
            worksheet,
            table_start_row,
            table_end_row,
            _COLUMN_ITEM_START,
            _COLUMN_SECONDARY,
        )
    if summary_end_row >= summary_start_row:
        _apply_grid_border(
            worksheet,
            summary_start_row,
            summary_end_row,
            _COLUMN_ITEM_START,
            _COLUMN_ITEM_START + 1,
        )

    workbook.save(output_path)
    return output_path


__all__ = ["RouteExcelItem", "RouteExcelRow", "export_route_to_excel", "DEFAULT_TEMPLATE"]

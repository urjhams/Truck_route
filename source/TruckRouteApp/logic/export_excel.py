"""
Utility helpers for exporting the computed route into an Excel workbook.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.xlsx"


@dataclass
class RouteExcelRow:
    order: int
    stop_name: str
    address: str
    lat: float
    lng: float
    distance_to_next_m: int
    items_summary: str = ""


def _load_or_create_template(path: Path) -> Workbook:
    if path.exists():
        return load_workbook(path)

    wb = Workbook()
    ws = wb.active
    ws.title = "Route"
    ws.append(
        [
            "Stop #",
            "Name",
            "Address",
            "Latitude",
            "Longitude",
            "Distance to next (m)",
            "Items summary",
        ]
    )
    for idx in range(1, 8):
        ws.column_dimensions[get_column_letter(idx)].width = 20
    return wb


def export_route_to_excel(
    output_path: Path,
    rows: Sequence[RouteExcelRow],
    metadata: Optional[Mapping[str, str]] = None,
    template_path: Optional[Path] = None,
) -> Path:
    """
    Export the provided rows to an Excel file based on a template.
    """
    template = template_path or DEFAULT_TEMPLATE
    workbook = _load_or_create_template(template)
    worksheet = workbook.active

    metadata = metadata or {}
    meta_start_row = 1
    for key, value in metadata.items():
        worksheet.cell(row=meta_start_row, column=9, value=key)
        worksheet.cell(row=meta_start_row, column=10, value=value)
        meta_start_row += 1

    start_row = 2
    if worksheet.max_row > 1:
        start_row = worksheet.max_row + 1

    for idx, row in enumerate(rows, start=start_row):
        worksheet.cell(idx, 1, row.order)
        worksheet.cell(idx, 2, row.stop_name)
        worksheet.cell(idx, 3, row.address)
        worksheet.cell(idx, 4, row.lat)
        worksheet.cell(idx, 5, row.lng)
        worksheet.cell(idx, 6, row.distance_to_next_m)
        worksheet.cell(idx, 7, row.items_summary)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return output_path


__all__ = ["RouteExcelRow", "export_route_to_excel", "DEFAULT_TEMPLATE"]


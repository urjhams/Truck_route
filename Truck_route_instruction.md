# Truck Route Desktop App — Development Specification

## 1. Project Goal

Build a **fully offline desktop application** for planning delivery routes, storing customer & item data, and exporting delivery tickets to Excel.  
The app must run on **Windows (primary)** and **macOS (secondary)**, with no cloud dependency.

## 2. Core Features

| Feature | Description |
|---------|-------------|
| ✅ Local database | SQLite embedded file, no external server |
| ✅ GUI | Built with PySide6 (Qt) |
| ✅ CRUD screens | Users can add/edit/delete Warehouses, Customers, Items |
| ✅ Order creation | Select warehouse, select customers, enter quantities |
| ✅ Route optimization | Uses local OR-Tools TSP logic + Haversine distance |
| ✅ Manual override | User can rearrange route before export |
| ✅ Excel export | Fills a template `.xlsx` with route & item data |
| ✅ Packaged app | Single-file `.exe` for Windows, `.app` for macOS |

## 3. Tech Stack (locked)

| Layer | Library / Tool |
|--------|----------------|
| Language | Python 3.12 |
| GUI | PySide6 (Qt for Python) |
| Routing Engine | `ortools` (TSP first, later CVRP optional) |
| Local Distance | Haversine (no API calls) |
| Database | SQLite (`sqlmodel` ORM) |
| Excel Output | `openpyxl` |
| Packaging | PyInstaller (Windows + macOS) |

## 4. SQLite Schema

```sql
WAREHOUSES(
    id INTEGER PRIMARY KEY,
    name TEXT,
    address TEXT,
    lat REAL,
    lng REAL
)

CUSTOMERS(
    id INTEGER PRIMARY KEY,
    name TEXT,
    address TEXT,
    lat REAL,
    lng REAL
)

ITEMS(
    id INTEGER PRIMARY KEY,
    name TEXT,
    weight_per_ctn REAL,
    ctn_per_pallet INTEGER
)

ORDERS(
    id INTEGER PRIMARY KEY,
    warehouse_id INTEGER REFERENCES WAREHOUSES(id),
    created_at TEXT
)

ORDER_LINES(
    id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES ORDERS(id),
    customer_id INTEGER REFERENCES CUSTOMERS(id),
    item_id INTEGER REFERENCES ITEMS(id),
    qty INTEGER
)
```

## 5. GUI Requirements

✅ Main window with navigation sidebar:

- Warehouses
- Customers
- Items
- Orders

✅ CRUD Table screens:

- Editable table grid
- Add / Edit / Delete buttons
- Data auto-committed to SQLite

✅ Order creation UI:

- Select warehouse (dropdown)
- Multi-select customers (checkbox list)
- Item entry per customer (popup or inline table)
- "Estimate Route" button (calls routing module)
- Route preview list (sortable by drag & drop)

✅ Export UI:

- Shows preview grid of final route
- "Export to Excel" button  
- Uses bundled Excel template (`assets/template.xlsx`)
- Save dialog for export file

## 6. Routing Specification

- Input: warehouse + list of customer coordinates
- Distance: `haversine_meters()` (already implemented)
- Optimization: OR-Tools TSP, return-to-depot enabled by default
- Output: ordered list of stop nodes + CSV/Excel-ready rows
- Reject invalid lat/lng before routing
- If only 1 customer, no optimization needed

## 7. App Structure Proposal

```plaintext
TruckRouteApp/
│── main.py                  # GUI entry point
│── db/
│   └── truckroute.db        # SQLite file (created on first run)
│── models/
│   └── schema.py            # SQLModel definitions
│── ui/
│   ├── main_window.ui       # Qt Designer file (optional)
│   ├── edit_customer.ui
│   ├── edit_item.ui
│   └── order_create.ui
│── logic/
│   ├── routing_local.py     # existing routing code wrapped into module
│   ├── db_access.py         # CRUD helpers
│   └── export_excel.py      # export into template.xlsx
│── assets/
│   └── template.xlsx
│── build/                   # (generated when packaging)
└── README.md
```

## 8. Packaging Requirements

Target build output:

```plaintext
dist/TruckRoute.exe      (Windows)
dist/TruckRoute.app      (macOS)
```

Bundled inside executable:
✅ Python runtime  
✅ Qt runtime  
✅ SQLite DB file (bootstraps if not exists)  
✅ Excel template  
✅ Icons, assets  

User should **not** need Python installed.

## 9. Implementation Roadmap

| Step | Module |
|------|--------|
| 1 | Create SQLite models + DB bootstrap file |
| 2 | Build CRUD utilities (db_access.py) |
| 3 | Wrap routing_local.py into class/module |
| 4 | Implement PySide6 window + table views |
| 5 | Add Order creation flow + route preview UI |
| 6 | Add Excel export module |
| 7 | Bundle app via PyInstaller |
| 8 | Add settings, polishing, icons, installer (optional) |

## 10. Future Extensions

- ✅ Add vehicle capacity (CVRP)
- ✅ Add ORS / OSRM network routing later
- ✅ Add barcode / QR code on Excel exports
- ✅ Add user login w/ role permissions
- ✅ Add template editor for Excel layout

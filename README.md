# Truck Route Planner

An offline-first desktop application for planning truck deliveries. The app stores warehouses, customers, items and orders in a local SQLite database, optimises a delivery tour with OR-Tools, and exports the final plan to Excel and pallet labels to DOCX so drivers can leave without any cloud dependency.

## Feature Tour

- **Multi-tenant CRUD** – Manage warehouses, customers, items and orders via PySide6 tables with CSV import helpers.
- **Order workflow** – Build orders by combining customers + items, estimate pallet counts, and preview the trip.
- **Route optimisation** – Local OR-Tools TSP solver uses Haversine distance to order stops; drag-and-drop can fine tune the result.
- **Exports** – Generate a styled Excel route sheet and pallet DOCX tickets plus full database export/import for backups.
- **Internationalisation** – Lightweight i18n system with live language switching (English/German by default).
- **Packaging** – Ships as a PyInstaller bundle for Windows (.exe) and macOS (.app) with all dependencies inside.

## High-Level Flow

1. **Startup** – `source/TruckRouteApp/main.py` initialises the SQLite database (or bootstraps from `assets/truckroute.db`) and launches the Qt event loop.
2. **CRUD screens** – `ui.views` exposes four `BaseCrudView` subclasses (Warehouses, Customers, Items, Orders) that call into `logic.db_access.DatabaseService` for persistence.
3. **Order building** – `ui.order_dialog.OrderDialog` lets the dispatcher add lines, validates pallet/carton ratios, and continuously mirrors the in-memory cart in the table.
4. **Routing** – When the user triggers “Estimate route” we launch `logic.routing_local.optimise_route` on a background thread. The ordered stops hydrate the route preview list which the user may reorder manually.
5. **Export** –
   - **Excel**: `logic.export_excel.export_route_to_excel` fills `assets/template.xlsx`, injects the logo image, and writes per-stop blocks.
   - **DOCX**: `logic.export_docx.export_pallets_to_docx` clones `assets/Template.docx` and replaces placeholders per pallet ticket.
6. **Backups** – Sidebar buttons call `DatabaseService.export_database` / `import_database` so users can share or restore the SQLite file safely.

## Architecture & Directory Map

```plantext
source/TruckRouteApp/
├── main.py                # Qt entry point
├── db/                    # SQLite bootstrap + seed database
├── logic/                 # Domain logic (CRUD wrapper, routing, exports)
├── models/                # SQLModel schema definitions
├── ui/                    # PySide6 widgets, dialogs, translations
└── assets/                # Excel/DOCX templates, seed database, icons
```

Key modules:

- `db/bootstrap.py` – figures out the writable DB path (dev vs packaged), copies the seed DB, runs lightweight migrations, and exposes `session_context`.
- `logic/db_access.py` – high-level CRUD surface so the UI never manipulates SQL sessions directly; also contains DB import/export helpers.
- `logic/routing_local.py` – OR-Tools TSP wrapper that validates coordinates, builds a Haversine matrix, and returns ordered stops + total distance.
- `logic/export_excel.py` / `logic/export_docx.py` – glue around `openpyxl` and `python-docx` for the two export formats.
- `ui/base.py` + `ui/table_models.py` – shared Qt widgets/utilities used by all CRUD views.
- `ui/dialogs.py` – modal editors for warehouses/customers/items and CSV mapping utilities.
- `ui/order_dialog.py` – orchestrates order creation, routing, exports, and pallet ticket logic.
- `ui/i18n.py` – tiny translation catalog with runtime language switching.

## Data Model Overview

The SQLModel schema (`models/schema.py`) mirrors the business entities:

- `Warehouse` (id, name, address, lat, lng) – start/end depots.
- `Customer` (id string, optional coordinates) – delivery stops.
- `Item` (id string, packing & pricing metadata) – referenced by order lines.
- `Order` (string id generated as `DDMMYYYY#`, `warehouse_id`, timestamp).
- `OrderLine` (links orders → customers → items, with pallet and carton info).

## Developing Locally

1. **Prerequisites**
   - Python 3.12
   - A virtual environment (recommended)
2. **Install dependencies**

   ```bash
   pip install PySide6 sqlmodel sqlalchemy openpyxl ortools python-docx
   ```

3. **Run the app**

   ```bash
   python -m source.TruckRouteApp.main
   ```

4. **Tests** – The repository includes sample spreadsheets/docs under `test/` for manual verification; automated tests can be run with `pytest` if added.

## Packaging with PyInstaller

A ready-to-use spec file lives at the repo root (`TruckRouteApp.spec`). Typical commands:

```bash
# macOS .app bundle
pyinstaller TruckRouteApp.spec --noconfirm --clean

# Windows .exe
pyinstaller TruckRouteApp.spec --noconfirm --clean
```

The spec already collects hidden imports for OR-Tools + SQLModel and bundles any assets declared in `datas` (add templates/icons there before building).

## Runtime Assets & Database Tips

- Seed database: `source/TruckRouteApp/db/truckroute.db`. When running from source it sits next to the bootstrap module; packaged builds copy it to the user’s AppData/Library folder.
- Templates: Excel (`assets/template.xlsx`), DOCX (`assets/Template.docx`), and any logos live under `source/TruckRouteApp/assets/`.
- Imports/exports: Use the sidebar buttons in the main window to move the SQLite file around (handy for backups or migrating data between machines).
- CSV import mapping: both Customers and Items screens expose an `Import CSV` button that launches the mapping dialog so headers can be aligned without editing the file.

## Troubleshooting

- **Missing python-docx / openpyxl** – Install the dependencies listed above; the exporters fail fast with a helpful message if the modules are absent.
- **Routing errors** – Ensure every selected customer has valid lat/lng coordinates; the route dialog validates them before launching OR-Tools.
- **Old databases** – When importing a legacy DB, `init_db` runs lightweight migrations automatically so no manual SQL is required.

"""
SQLite bootstrap utilities.
"""

from __future__ import annotations

import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlmodel import Session, SQLModel, create_engine

from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse

def get_app_db_path() -> Path:
    """
    Return the correct writable path for the SQLite DB depending on environment:
    - When frozen (PyInstaller exe/app), use OS-specific app data directory.
    - When running from source, use local db/ folder next to source files.
    """
    if getattr(sys, "frozen", False):  # Bundled app
        base = Path.home()
        if sys.platform == "darwin":
            base = base / "Library" / "Application Support" / "TruckRoute"
        elif sys.platform == "win32":
            base = base / "AppData" / "Roaming" / "TruckRoute"
        else:
            base = base / ".local" / "share" / "TruckRoute"
        return base / "truckroute.db"
    else:
        # Dev mode: local db folder inside repo
        return Path(__file__).resolve().parent / "truckroute.db"


DEFAULT_DB_PATH = get_app_db_path()


def get_engine(db_path: Optional[Path] = None):
    """
    Return a SQLAlchemy engine bound to the SQLite database.
    Ensures the parent directory exists.
    """
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", echo=False)

def _asset_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name

def _bootstrap_seed_db(db_path: Path) -> None:
    if db_path.exists():
        return
    seed = _asset_path("truckroute.db")
    if seed.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed, db_path)
        return
    # No bundled seed – create an empty file so SQLModel can initialize schema.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.touch(exist_ok=True)

def init_db(db_path: Optional[Path] = None) -> None:
    """
    Create database tables if they do not already exist.
    """
    _bootstrap_seed_db(db_path := db_path or DEFAULT_DB_PATH)
    engine = get_engine(db_path)
    _run_migrations(engine)
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_context(db_path: Optional[Path] = None) -> Iterator[Session]:
    """
    Context manager yielding a SQLModel session bound to the app engine.
    """
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session


def _run_migrations(engine) -> None:
    """
    Apply simple, in-place migrations needed for legacy database files.
    """
    with engine.begin() as conn:
        _ensure_customers_lat_lng_nullable(conn)
        _ensure_items_optional_columns(conn)
        _ensure_order_lines_item_id_text(conn)
        _ensure_order_lines_ktn_column(conn)
        _ensure_orders_id_text(conn)


def _ensure_customers_lat_lng_nullable(conn) -> None:
    table_exists = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='CUSTOMERS';"
    ).fetchone()
    if not table_exists:
        return

    columns = conn.exec_driver_sql('PRAGMA table_info("CUSTOMERS");').fetchall()
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    col_meta = {row[1].lower(): row for row in columns}
    needs_migration = False
    for key in ("lat", "lng"):
        row = col_meta.get(key)
        if row and row[3] == 1:  # notnull flag
            needs_migration = True
            break

    id_meta = col_meta.get("id")
    id_needs_text = id_meta and (id_meta[2] or "").upper() != "TEXT"

    if not needs_migration and not id_needs_text:
        return

    conn.exec_driver_sql("PRAGMA foreign_keys=off;")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS __CUSTOMERS_NEW (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            lat REAL,
            lng REAL
        );
        """
    )
    conn.exec_driver_sql(
        """
        INSERT INTO __CUSTOMERS_NEW (id, name, address, lat, lng)
        SELECT id, name, address, lat, lng FROM CUSTOMERS;
        """
    )
    conn.exec_driver_sql("DROP TABLE CUSTOMERS;")
    conn.exec_driver_sql('ALTER TABLE __CUSTOMERS_NEW RENAME TO "CUSTOMERS";')
    conn.exec_driver_sql("PRAGMA foreign_keys=on;")


def _ensure_items_optional_columns(conn) -> None:
    table_exists = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ITEMS';"
    ).fetchone()
    if not table_exists:
        return

    columns = conn.exec_driver_sql('PRAGMA table_info("ITEMS");').fetchall()
    existing = {row[1].lower(): row for row in columns}
    items_meta = existing.get("items_per_ktn")
    if items_meta and (items_meta[2] or "").upper() != "TEXT":
        _rebuild_items_table(conn)
        return
    tax_meta = existing.get("tax")
    if tax_meta and (tax_meta[2] or "").upper() != "TEXT":
        _rebuild_items_table(conn)
        return
    id_meta = existing.get("id")
    if id_meta and (id_meta[2] or "").upper() != "TEXT":
        _rebuild_items_table(conn)
        return

    required_columns = {
        "ktn_per_pal": "INTEGER",
        "items_per_ktn": "TEXT",
        "price_gross": "REAL",
        "price_net": "REAL",
        "tax": "TEXT",
    }
    for col_name, col_type in required_columns.items():
        if col_name not in existing:
            conn.exec_driver_sql(f'ALTER TABLE "ITEMS" ADD COLUMN {col_name} {col_type};')


def _rebuild_items_table(conn) -> None:
    conn.exec_driver_sql("PRAGMA foreign_keys=off;")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS __ITEMS_NEW (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ktn_per_pal INTEGER,
            items_per_ktn TEXT,
            price_gross REAL,
            price_net REAL,
            tax TEXT
        );
        """
    )
    columns = conn.exec_driver_sql('PRAGMA table_info("ITEMS");').fetchall()
    existing = {row[1].lower() for row in columns}

    select_parts = [
        "CAST(id AS TEXT) AS id",
        "name",
        "ktn_per_pal" if "ktn_per_pal" in existing else "NULL AS ktn_per_pal",
        (
            """
            CASE
                WHEN items_per_ktn IS NULL THEN NULL
                ELSE CAST(items_per_ktn AS TEXT)
            END AS items_per_ktn
            """.strip()
            if "items_per_ktn" in existing
            else "NULL AS items_per_ktn"
        ),
        "price_gross" if "price_gross" in existing else "NULL AS price_gross",
        "price_net" if "price_net" in existing else "NULL AS price_net",
        (
            """
            CASE
                WHEN tax IS NULL THEN NULL
                ELSE CAST(tax AS TEXT)
            END AS tax
            """.strip()
            if "tax" in existing
            else "NULL AS tax"
        ),
    ]

    select_clause = ",\n            ".join(select_parts)

    conn.exec_driver_sql(
        """
        INSERT INTO __ITEMS_NEW (id, name, ktn_per_pal, items_per_ktn, price_gross, price_net, tax)
        SELECT
            {select_clause}
        FROM ITEMS;
        """
        .format(select_clause=select_clause)
    )
    conn.exec_driver_sql("DROP TABLE ITEMS;")
    conn.exec_driver_sql('ALTER TABLE __ITEMS_NEW RENAME TO "ITEMS";')
    conn.exec_driver_sql("PRAGMA foreign_keys=on;")


def _ensure_order_lines_item_id_text(conn) -> None:
    table_exists = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ORDER_LINES';"
    ).fetchone()
    if not table_exists:
        return

    columns = conn.exec_driver_sql('PRAGMA table_info("ORDER_LINES");').fetchall()
    col_meta = {row[1].lower(): row for row in columns}
    customer_meta = col_meta.get("customer_id")
    item_meta = col_meta.get("item_id")
    needs_customer_text = customer_meta and (customer_meta[2] or "").upper() != "TEXT"
    needs_item_text = item_meta and (item_meta[2] or "").upper() != "TEXT"
    if not needs_customer_text and not needs_item_text:
        # Ensure pallets/ktn columns exist even if text conversion not required
        if "pallets" not in col_meta or "ktn_per_pal" not in col_meta:
            _rebuild_order_lines_table(conn, convert_text=False)
        return

    _rebuild_order_lines_table(conn, convert_text=True)


def _rebuild_order_lines_table(conn, convert_text: bool) -> None:
    conn.exec_driver_sql("PRAGMA foreign_keys=off;")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS __ORDER_LINES_NEW (
            id INTEGER PRIMARY KEY,
            order_id TEXT REFERENCES ORDERS(id),
            customer_id TEXT REFERENCES CUSTOMERS(id),
            item_id TEXT REFERENCES ITEMS(id),
            pallets REAL NOT NULL DEFAULT 0.0,
            ktn_per_pal REAL
        );
        """
    )
    columns = conn.exec_driver_sql('PRAGMA table_info("ORDER_LINES");').fetchall()
    existing = {row[1].lower() for row in columns}

    order_id_select = (
        "CAST(order_id AS TEXT) AS order_id" if convert_text else "order_id"
    )
    customer_id_select = (
        "CAST(customer_id AS TEXT) AS customer_id" if convert_text else "customer_id"
    )
    item_id_select = (
        "CAST(item_id AS TEXT) AS item_id" if convert_text else "item_id"
    )
    pallets_select = "pallets" if "pallets" in existing else "0.0 AS pallets"
    ktn_select = (
        "ktn_per_pal" if "ktn_per_pal" in existing else "NULL AS ktn_per_pal"
    )

    conn.exec_driver_sql(
        f"""
        INSERT INTO __ORDER_LINES_NEW (id, order_id, customer_id, item_id, pallets, ktn_per_pal)
        SELECT
            id,
            {order_id_select},
            {customer_id_select},
            {item_id_select},
            {pallets_select},
            {ktn_select}
        FROM ORDER_LINES;
        """
    )
    conn.exec_driver_sql("DROP TABLE ORDER_LINES;")
    conn.exec_driver_sql('ALTER TABLE __ORDER_LINES_NEW RENAME TO "ORDER_LINES";')
    conn.exec_driver_sql("PRAGMA foreign_keys=on;")


def _ensure_order_lines_ktn_column(conn) -> None:
    table_exists = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ORDER_LINES';"
    ).fetchone()
    if not table_exists:
        return

    columns = conn.exec_driver_sql('PRAGMA table_info("ORDER_LINES");').fetchall()
    existing = {row[1].lower() for row in columns}
    if "ktn_per_pal" in existing:
        return
    conn.exec_driver_sql('ALTER TABLE "ORDER_LINES" ADD COLUMN ktn_per_pal REAL;')


def _ensure_orders_id_text(conn) -> None:
    table_exists = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ORDERS';"
    ).fetchone()
    if not table_exists:
        return

    columns = conn.exec_driver_sql('PRAGMA table_info("ORDERS");').fetchall()
    col_meta = {row[1].lower(): row for row in columns}
    id_meta = col_meta.get("id")
    if not id_meta:
        return
    if (id_meta[2] or "").upper() == "TEXT":
        return

    conn.exec_driver_sql("PRAGMA foreign_keys=off;")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS __ORDERS_NEW (
            id TEXT PRIMARY KEY,
            warehouse_id INTEGER REFERENCES WAREHOUSES(id),
            created_at TEXT
        );
        """
    )
    conn.exec_driver_sql(
        """
        INSERT INTO __ORDERS_NEW (id, warehouse_id, created_at)
        SELECT CAST(id AS TEXT), warehouse_id, created_at
        FROM ORDERS;
        """
    )
    conn.exec_driver_sql("DROP TABLE ORDERS;")
    conn.exec_driver_sql('ALTER TABLE __ORDERS_NEW RENAME TO "ORDERS";')
    conn.exec_driver_sql("PRAGMA foreign_keys=on;")


__all__ = [
    "DEFAULT_DB_PATH",
    "get_engine",
    "init_db",
    "session_context",
    "Warehouse",
    "Customer",
    "Item",
    "Order",
    "OrderLine",
]

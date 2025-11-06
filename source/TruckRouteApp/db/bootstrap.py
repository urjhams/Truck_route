"""
SQLite bootstrap utilities.
"""

from __future__ import annotations

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


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Create database tables if they do not already exist.
    """
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

    if not needs_migration:
        return

    conn.exec_driver_sql("PRAGMA foreign_keys=off;")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS __CUSTOMERS_NEW (
            id INTEGER PRIMARY KEY,
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
    # Use COALESCE to support legacy numeric columns.
    conn.exec_driver_sql(
        """
        INSERT INTO __ITEMS_NEW (id, name, ktn_per_pal, items_per_ktn, price_gross, price_net, tax)
        SELECT
            CAST(id AS TEXT),
            name,
            ktn_per_pal,
            CASE
                WHEN items_per_ktn IS NULL THEN NULL
                ELSE CAST(items_per_ktn AS TEXT)
            END,
            price_gross,
            price_net,
            CASE
                WHEN tax IS NULL THEN NULL
                ELSE CAST(tax AS TEXT)
            END
        FROM ITEMS;
        """
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
    item_meta = col_meta.get("item_id")
    if not item_meta:
        return
    if (item_meta[2] or "").upper() == "TEXT":
        return

    conn.exec_driver_sql("PRAGMA foreign_keys=off;")
    conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS __ORDER_LINES_NEW (
            id INTEGER PRIMARY KEY,
            order_id INTEGER REFERENCES ORDERS(id),
            customer_id INTEGER REFERENCES CUSTOMERS(id),
            item_id TEXT REFERENCES ITEMS(id),
            pallets REAL NOT NULL DEFAULT 0.0
        );
        """
    )
    conn.exec_driver_sql(
        """
        INSERT INTO __ORDER_LINES_NEW (id, order_id, customer_id, item_id, pallets)
        SELECT id, order_id, customer_id, CAST(item_id AS TEXT), pallets
        FROM ORDER_LINES;
        """
    )
    conn.exec_driver_sql("DROP TABLE ORDER_LINES;")
    conn.exec_driver_sql('ALTER TABLE __ORDER_LINES_NEW RENAME TO "ORDER_LINES";')
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

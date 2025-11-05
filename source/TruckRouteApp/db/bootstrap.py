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
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_context(db_path: Optional[Path] = None) -> Iterator[Session]:
    """
    Context manager yielding a SQLModel session bound to the app engine.
    """
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session


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
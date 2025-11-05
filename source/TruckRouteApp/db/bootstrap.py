"""
SQLite bootstrap utilities.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlmodel import Session, SQLModel, create_engine

from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse

# Default location for the SQLite database. The file is created lazily.
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "truckroute.db"


def get_engine(db_path: Optional[Path] = None):
    """
    Return a SQLAlchemy engine bound to the local SQLite database.

    The function ensures the parent directory exists so the database file can be
    created on first use.
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
    Context manager yielding a SQLModel session bound to the application engine.
    """
    engine = get_engine(db_path)
    with Session(engine) as session:
        yield session


__all__ = [
    "DEFAULT_DB_PATH",
    "get_engine",
    "init_db",
    "session_context",
    # Explicitly import models to make them available through this module.
    "Warehouse",
    "Customer",
    "Item",
    "Order",
    "OrderLine",
]


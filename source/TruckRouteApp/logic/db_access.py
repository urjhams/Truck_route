"""
High level CRUD helpers built on top of SQLModel sessions.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import shutil
from pathlib import Path
from typing import Generator, List, Optional, Sequence

from sqlalchemy import func, cast, String
from sqlmodel import Session, select, desc

from TruckRouteApp.db import DEFAULT_DB_PATH, session_context, init_db
from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse


class DatabaseService:
    """
    Convenience layer that centralises CRUD operations for the GUI layer.
    """

    def __init__(self, db_path=None):
        self._db_path = Path(db_path or DEFAULT_DB_PATH)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with session_context(self._db_path) as session:
            yield session

    # --- Warehouses -----------------------------------------------------
    def list_warehouses(self) -> List[Warehouse]:
        with self.session() as session:
            return list(session.exec(select(Warehouse).order_by(Warehouse.name)).all())

    def get_warehouse(self, warehouse_id: int) -> Optional[Warehouse]:
        with self.session() as session:
            return session.get(Warehouse, warehouse_id)

    def save_warehouse(self, warehouse: Warehouse) -> Warehouse:
        with self.session() as session:
            session.add(warehouse)
            session.commit()
            session.refresh(warehouse)
            return warehouse

    def delete_warehouse(self, warehouse_id: int) -> None:
        with self.session() as session:
            warehouse = session.get(Warehouse, warehouse_id)
            if warehouse:
                session.delete(warehouse)
                session.commit()

    # --- Customers ------------------------------------------------------
    def list_customers(self) -> List[Customer]:
        with self.session() as session:
            return list(session.exec(select(Customer).order_by(Customer.name)).all())

    def save_customer(self, customer: Customer) -> Customer:
        with self.session() as session:
            session.add(customer)
            session.commit()
            session.refresh(customer)
            return customer

    def customer_exists(self, name: str, address: Optional[str]) -> bool:
        """
        Return True when a customer with the same name/address already exists.
        Comparison is case-insensitive and treats missing addresses as blank.
        """
        normalized_name = name.strip().lower()
        normalized_address = (address or "").strip().lower()
        with self.session() as session:
            stmt = (
                select(Customer.id)
                .where(func.lower(Customer.name) == normalized_name)
                .where(func.lower(func.coalesce(Customer.address, "")) == normalized_address)
                .limit(1)
            )
            return session.exec(stmt).first() is not None

    def delete_customer(self, customer_id: str) -> None:
        with self.session() as session:
            customer = session.get(Customer, customer_id)
            if customer:
                session.delete(customer)
                session.commit()

    # --- Items ----------------------------------------------------------
    def list_items(self) -> List[Item]:
        with self.session() as session:
            return list(session.exec(select(Item).order_by(Item.id)).all())

    def save_item(self, item: Item) -> Item:
        with self.session() as session:
            if item.id is not None:
                existing = session.get(Item, item.id)
                if existing:
                    existing.name = item.name
                    existing.ktn_per_pal = item.ktn_per_pal
                    existing.items_per_ktn = item.items_per_ktn
                    existing.price_gross = item.price_gross
                    existing.price_net = item.price_net
                    existing.tax = item.tax
                    session.commit()
                    session.refresh(existing)
                    return existing
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def delete_item(self, item_id: str) -> None:
        with self.session() as session:
            item = session.get(Item, item_id)
            if item:
                session.delete(item)
                session.commit()

    # --- Orders ---------------------------------------------------------
    def list_orders(self) -> List[Order]:
        with self.session() as session:
            return list(session.exec(select(Order).order_by(desc(Order.created_at))).all())

    def get_order(self, order_id: str) -> Optional[Order]:
        with self.session() as session:
            return session.get(Order, order_id)

    def create_order_with_lines(
        self,
        order: Order,
        lines: Sequence[OrderLine],
    ) -> Order:
        with self.session() as session:
            if order.id is None:
                order.id = self._generate_order_id(session, order.created_at)
            session.add(order)
            for line in lines:
                line.order_id = order.id
                session.add(line)
            session.commit()
            session.refresh(order)
            return order

    def update_order_with_lines(
        self,
        order: Order,
        lines: Sequence[OrderLine],
    ) -> Order:
        if order.id is None:
            raise ValueError("Order must have an ID to update.")
        with self.session() as session:
            existing = session.get(Order, order.id)
            if not existing:
                raise ValueError(f"Order '{order.id}' does not exist.")
            existing.warehouse_id = order.warehouse_id

            current_lines = session.exec(
                select(OrderLine).where(OrderLine.order_id == order.id)
            ).all()
            for line in current_lines:
                session.delete(line)

            for line in lines:
                line.order_id = order.id
                session.add(line)

            session.commit()
            session.refresh(existing)
            return existing

    def list_order_lines(self, order_id: str) -> List[OrderLine]:
        with self.session() as session:
            return list(session.exec(
                select(OrderLine).where(OrderLine.order_id == order_id)
            ).all())

    def delete_order(self, order_id: str) -> None:
        with self.session() as session:
            order = session.get(Order, order_id)
            if order:
                lines = session.exec(
                    select(OrderLine).where(OrderLine.order_id == order_id)
                ).all()
                for line in lines:
                    session.delete(line)
                session.delete(order)
                session.commit()

    def _generate_order_id(self, session: Session, created_at: datetime) -> str:
        prefix = created_at.strftime("%d%m%Y")
        stmt = select(Order.id).where(cast(Order.id, String).like(f"{prefix}%"))
        existing_ids = session.exec(stmt).all()
        max_suffix = 0
        for value in existing_ids:
            if value is not None and isinstance(value, str) and value.startswith(prefix):
                suffix = value[len(prefix):]
                if suffix.isdigit():
                    max_suffix = max(max_suffix, int(suffix))
        return f"{prefix}{max_suffix + 1}"

    # --- Database backup/restore ---------------------------------------
    def export_database(self, destination: Path | str) -> Path:
        """
        Copy the SQLite database file to the requested destination path.
        Returns the resolved destination path.
        """
        dest_path = Path(destination).expanduser().resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._db_path, dest_path)
        return dest_path

    def import_database(self, source: Path | str) -> Path:
        """
        Replace the current SQLite database file with the provided source file.
        Runs lightweight migrations after copying to keep schemas aligned.
        Returns the resolved destination path.
        """
        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Database import file not found: {source_path}")
        destination = self._db_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        init_db(destination)  # ensure schema/migrations applied
        return destination


__all__ = ["DatabaseService"]

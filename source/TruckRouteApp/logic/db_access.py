"""
High level CRUD helpers built on top of SQLModel sessions.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import re
import secrets
import shutil
from pathlib import Path
from typing import Generator, List, Optional, Sequence, Type

from sqlalchemy import func, cast, String
from sqlmodel import Session, SQLModel, select, desc

from TruckRouteApp.db import DEFAULT_DB_PATH, session_context, init_db
from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse


class DatabaseService:
    """
    Convenience layer that centralises CRUD operations for the GUI layer.
    Every method keeps the UI code free from SQLModel boilerplate and ensures
    sessions are short-lived (open per action).
    """

    def __init__(self, db_path=None):
        self._db_path = Path(db_path or DEFAULT_DB_PATH)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        # The UI never holds onto sessions directly; instead we expose a
        # context manager so each action runs in its own transaction.
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
            # ``session.add`` works for both inserts and updates; SQLModel
            # figures out whether ``warehouse.id`` is already present.
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

    def save_customer(self, customer: Customer, original_id: Optional[str] = None) -> Customer:
        with self.session() as session:
            desired_id = (customer.id or "").strip() or None
            if original_id:
                db_customer = session.get(Customer, original_id)
                if not db_customer:
                    raise ValueError("customer_not_found")
                new_id = desired_id or self._generate_incremental_id(session, Customer, customer.name, "CUS")
                if new_id != original_id and session.get(Customer, new_id):
                    raise ValueError("duplicate_customer_id")
                db_customer.id = new_id
                db_customer.name = customer.name
                db_customer.address = customer.address
                db_customer.lat = customer.lat
                db_customer.lng = customer.lng
                session.commit()
                session.refresh(db_customer)
                return db_customer

            new_id = desired_id or self._generate_incremental_id(session, Customer, customer.name, "CUS")
            if session.get(Customer, new_id):
                raise ValueError("duplicate_customer_id")
            customer.id = new_id
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
        self.delete_customers([customer_id])

    def delete_customers(self, customer_ids: Sequence[str]) -> int:
        ids = [customer_id for customer_id in customer_ids if customer_id]
        if not ids:
            return 0
        with self.session() as session:
            rows = session.exec(
                select(Customer).where(Customer.id.in_(ids))
            ).all()
            deleted = 0
            for customer in rows:
                session.delete(customer)
                deleted += 1
            if deleted:
                # Only commit when we actually removed rows so read-only requests
                # do not bump the write-ahead log unnecessarily.
                session.commit()
            return deleted

    # --- Items ----------------------------------------------------------
    def list_items(self) -> List[Item]:
        with self.session() as session:
            return list(session.exec(select(Item).order_by(Item.id)).all())

    def save_item(self, item: Item, original_id: Optional[str] = None) -> Item:
        with self.session() as session:
            desired_id = (item.id or "").strip() or None
            if original_id:
                existing = session.get(Item, original_id)
                if not existing:
                    raise ValueError("item_not_found")
                new_id = desired_id or self._generate_incremental_id(session, Item, item.name, "ITEM")
                if new_id != original_id and session.get(Item, new_id):
                    raise ValueError("duplicate_item_id")
                existing.id = new_id
                existing.name = item.name
                existing.ktn_per_pal = item.ktn_per_pal
                existing.items_per_ktn = item.items_per_ktn
                existing.price_gross = item.price_gross
                existing.price_net = item.price_net
                existing.tax = item.tax
                session.commit()
                session.refresh(existing)
                return existing

            new_id = desired_id or self._generate_incremental_id(session, Item, item.name, "ITEM")
            if session.get(Item, new_id):
                raise ValueError("duplicate_item_id")
            item.id = new_id
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def delete_item(self, item_id: str) -> None:
        self.delete_items([item_id])

    def delete_items(self, item_ids: Sequence[str]) -> int:
        ids = [item_id for item_id in item_ids if item_id]
        if not ids:
            return 0
        with self.session() as session:
            rows = session.exec(
                select(Item).where(Item.id.in_(ids))
            ).all()
            deleted = 0
            for item in rows:
                session.delete(item)
                deleted += 1
            if deleted:
                session.commit()
            return deleted

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
                # Orders created from the UI do not come with IDs; use the
                # creation date to generate a sequential daily identifier.
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
            # Simplest approach: wipe the existing lines and re-create them
            # from the payload the dialog sends back.
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

    def _generate_incremental_id(
        self,
        session: Session,
        model: Type[SQLModel],
        name: Optional[str],
        prefix: str,
    ) -> str:
        """
        Build a readable identifier derived from ``name`` and ensure uniqueness in the table.
        Falls back to ``prefix`` when the provided name does not contain alphanumerics.
        """
        cleaned = re.sub(r"[^A-Z0-9]", "", (name or "").upper())
        base = (cleaned or prefix).strip() or prefix
        base = base[:8] or prefix
        candidate = base
        suffix = 1
        while session.get(model, candidate):
            candidate = f"{base}{suffix:02d}"
            suffix += 1
            if suffix > 99:
                random_chunk = secrets.token_hex(2).upper()
                keep = max(0, 10 - len(random_chunk))
                candidate = f"{base[:keep]}{random_chunk}"
                suffix = 1
        return candidate

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
        # Order IDs produce human-readable batches such as DDMMYYYY1, DDMMYYYY2, ...
        return f"{prefix}{max_suffix + 1}"

    # --- Database backup/restore ---------------------------------------
    def export_database(self, destination: Path | str) -> Path:
        """
        Copy the SQLite database file to the requested destination path.
        Returns the resolved destination path.
        """
        dest_path = Path(destination).expanduser().resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # ``copy2`` keeps file metadata intact which makes debugging easier
        # when users send exported DBs back.
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
        # After copying we still init/migrate to make sure older exports get
        # patched to the current schema automatically.
        init_db(destination)  # ensure schema/migrations applied
        return destination


__all__ = ["DatabaseService"]

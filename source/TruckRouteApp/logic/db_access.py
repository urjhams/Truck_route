"""
High level CRUD helpers built on top of SQLModel sessions.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, List, Optional, Sequence

from sqlalchemy import func
from sqlmodel import Session, select, desc

from TruckRouteApp.db import DEFAULT_DB_PATH, session_context
from TruckRouteApp.models.schema import Customer, Item, Order, OrderLine, Warehouse


class DatabaseService:
    """
    Convenience layer that centralises CRUD operations for the GUI layer.
    """

    def __init__(self, db_path=None):
        self._db_path = db_path or DEFAULT_DB_PATH

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

    def get_order(self, order_id: int) -> Optional[Order]:
        with self.session() as session:
            return session.get(Order, order_id)

    def create_order_with_lines(
        self,
        order: Order,
        lines: Sequence[OrderLine],
    ) -> Order:
        with self.session() as session:
            session.add(order)
            session.flush()  # ensure order.id is available for lines
            if order.id is None:
                raise ValueError("Order ID is None after flush")
            for line in lines:
                line.order_id = order.id
                session.add(line)
            session.commit()
            session.refresh(order)
            return order

    def list_order_lines(self, order_id: int) -> List[OrderLine]:
        with self.session() as session:
            return list(session.exec(
                select(OrderLine).where(OrderLine.order_id == order_id)
            ).all())

    def delete_order(self, order_id: int) -> None:
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


__all__ = ["DatabaseService"]

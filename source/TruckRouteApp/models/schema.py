"""
SQLModel schema definitions for the Truck Route application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

class Warehouse(SQLModel, table=True):
    __tablename__: str = "WAREHOUSES"
    __tablename__ = "WAREHOUSES"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    address: Optional[str] = Field(default=None)
    lat: float = Field(nullable=False)
    lng: float = Field(nullable=False)

class Customer(SQLModel, table=True):
    __tablename__: str = "CUSTOMERS"
    __tablename__ = "CUSTOMERS"

    id: Optional[str] = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    address: Optional[str] = Field(default=None)
    lat: Optional[float] = Field(default=None, nullable=True)
    lng: Optional[float] = Field(default=None, nullable=True)

class Item(SQLModel, table=True):
    __tablename__: str = "ITEMS"
    __tablename__ = "ITEMS"

    id: Optional[str] = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    ktn_per_pal: Optional[int] = Field(default=None)
    items_per_ktn: Optional[str] = Field(default=None)
    price_gross: Optional[float] = Field(default=None)
    price_net: Optional[float] = Field(default=None)
    tax: Optional[str] = Field(default=None)

class Order(SQLModel, table=True):
    __tablename__: str = "ORDERS"
    __tablename__ = "ORDERS"

    id: Optional[str] = Field(default=None, primary_key=True)
    warehouse_id: int = Field(foreign_key="WAREHOUSES.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class OrderLine(SQLModel, table=True):
    __tablename__: str = "ORDER_LINES"
    __tablename__ = "ORDER_LINES"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: str = Field(foreign_key="ORDERS.id", nullable=False)
    customer_id: str = Field(foreign_key="CUSTOMERS.id", nullable=False)
    item_id: str = Field(foreign_key="ITEMS.id", nullable=False)
    pallets: float = Field(default=0.0, nullable=False)
    ktn_per_pal: Optional[float] = Field(default=None, nullable=True)


__all__ = [
    "Warehouse",
    "Customer",
    "Item",
    "Order",
    "OrderLine",
]  # Re-export models for convenience.

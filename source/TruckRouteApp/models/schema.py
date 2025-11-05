"""
SQLModel schema definitions for the Truck Route application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel
from sqlalchemy.ext.declarative import declared_attr

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

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    address: Optional[str] = Field(default=None)
    lat: float = Field(nullable=False)
    lng: float = Field(nullable=False)

class Item(SQLModel, table=True):
    __tablename__: str = "ITEMS"
    __tablename__ = "ITEMS"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, nullable=False)
    weight_per_ctn: Optional[float] = Field(default=None)
    ctn_per_pallet: Optional[int] = Field(default=None)

class Order(SQLModel, table=True):
    __tablename__: str = "ORDERS"
    __tablename__ = "ORDERS"

    id: Optional[int] = Field(default=None, primary_key=True)
    warehouse_id: int = Field(foreign_key="WAREHOUSES.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

class OrderLine(SQLModel, table=True):
    __tablename__: str = "ORDER_LINES"
    __tablename__ = "ORDER_LINES"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="ORDERS.id", nullable=False)
    customer_id: int = Field(foreign_key="CUSTOMERS.id", nullable=False)
    item_id: int = Field(foreign_key="ITEMS.id", nullable=False)
    qty: int = Field(default=0, nullable=False)


__all__ = [
    "Warehouse",
    "Customer",
    "Item",
    "Order",
    "OrderLine",
]  # Re-export models for convenience.


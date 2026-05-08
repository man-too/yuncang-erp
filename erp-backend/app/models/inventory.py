"""库存管理模型"""
from datetime import datetime, date
from sqlalchemy import (
    String, Text, Float, Integer, DateTime, Date, func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class Warehouse(Base):
    """仓库"""
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(50), unique=True)
    address: Mapped[str] = mapped_column(String(500), default="")
    manager: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Inventory(Base):
    """库存（按仓库+产品）"""
    __tablename__ = "inventories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    locked_quantity: Mapped[float] = mapped_column(Float, default=0.0)  # 锁定数量
    available_quantity: Mapped[float] = mapped_column(Float, default=0.0)  # 可用数量
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventoryRecord(Base):
    """库存变动记录"""
    __tablename__ = "inventory_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer)
    change_type: Mapped[str] = mapped_column(String(50))  # inbound/outbound/adjustment
    change_quantity: Mapped[float] = mapped_column(Float)
    before_quantity: Mapped[float] = mapped_column(Float)
    after_quantity: Mapped[float] = mapped_column(Float)
    ref_type: Mapped[str] = mapped_column(String(50), default="")  # 关联单据类型
    ref_id: Mapped[int] = mapped_column(Integer, default=0)  # 关联单据ID
    operator_id: Mapped[int] = mapped_column(Integer)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InventoryAlert(Base):
    """库存预警记录"""
    __tablename__ = "inventory_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer)
    alert_type: Mapped[str] = mapped_column(String(50))  # low_stock / high_stock / overdue
    current_quantity: Mapped[float] = mapped_column(Float)
    threshold_value: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(20), default="warning")  # warning / critical
    is_resolved: Mapped[bool] = mapped_column(default=False)
    ai_suggestion: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

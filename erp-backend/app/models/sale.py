"""销售管理模型"""
from datetime import datetime, date
from sqlalchemy import (
    String, Text, Float, Integer, DateTime, Date, func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class SaleOrderStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PARTIALLY_SHIPPED = "partially_shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Customer(Base):
    """客户"""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    tax_id: Mapped[str] = mapped_column(String(50), default="")
    credit_limit: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(default=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SaleOrder(Base):
    """销售订单"""
    __tablename__ = "sale_orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[SaleOrderStatus] = mapped_column(
        SAEnum(SaleOrderStatus, name="so_status"), default=SaleOrderStatus.DRAFT
    )
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    shipped_amount: Mapped[float] = mapped_column(Float, default=0.0)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0)
    creator_id: Mapped[int] = mapped_column(Integer)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SaleOrderItem(Base):
    """销售订单明细"""
    __tablename__ = "sale_order_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    shipped_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float)
    total_price: Mapped[float] = mapped_column(Float)
    remark: Mapped[str] = mapped_column(Text, default="")


class SaleOutbound(Base):
    """销售出库单"""
    __tablename__ = "sale_outbounds"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    outbound_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer)
    operator_id: Mapped[int] = mapped_column(Integer)
    outbound_date: Mapped[date] = mapped_column(Date, default=date.today)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

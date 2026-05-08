"""采购管理模型"""
from datetime import datetime, date
from sqlalchemy import (
    String, Text, Float, Integer, DateTime, Date, func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "draft"              # 草稿
    PENDING_APPROVAL = "pending_approval"  # 待审批
    APPROVED = "approved"        # 已审批
    PARTIALLY_RECEIVED = "partially_received"  # 部分收货
    COMPLETED = "completed"      # 已完成
    CANCELLED = "cancelled"      # 已取消


class PurchaseOrder(Base):
    """采购订单"""
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        SAEnum(PurchaseOrderStatus, name="po_status"), default=PurchaseOrderStatus.DRAFT
    )
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    received_amount: Mapped[float] = mapped_column(Float, default=0.0)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0)
    creator_id: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PurchaseOrderItem(Base):
    """采购订单明细"""
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    received_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float)
    total_price: Mapped[float] = mapped_column(Float)
    remark: Mapped[str] = mapped_column(Text, default="")


class PurchaseInbound(Base):
    """采购入库单"""
    __tablename__ = "purchase_inbounds"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    inbound_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    warehouse_id: Mapped[int] = mapped_column(Integer)
    operator_id: Mapped[int] = mapped_column(Integer)
    inbound_date: Mapped[date] = mapped_column(Date, default=date.today)
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

"""供应商模型"""
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, DateTime, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class SupplierStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    BLACKLISTED = "blacklisted"


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[SupplierStatus] = mapped_column(
        SAEnum(SupplierStatus, name="supplier_status"), default=SupplierStatus.PENDING
    )
    tax_id: Mapped[str] = mapped_column(String(50), default="")
    payment_terms: Mapped[str] = mapped_column(String(200), default="")
    delivery_lead_time: Mapped[int] = mapped_column(Integer, default=7)  # 交期天数
    rating: Mapped[float] = mapped_column(Float, default=0.0)  # 综合评分
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplierContact(Base):
    """供应商联系人"""
    __tablename__ = "supplier_contacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    supplier_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(100), default="")
    is_primary: Mapped[bool] = mapped_column(default=False)


class SupplierEvaluation(Base):
    """供应商评估记录"""
    __tablename__ = "supplier_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    supplier_id: Mapped[int] = mapped_column(Integer, index=True)
    evaluator_id: Mapped[int] = mapped_column(Integer)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)  # 质量分
    delivery_score: Mapped[float] = mapped_column(Float, default=0.0)  # 交期分
    price_score: Mapped[float] = mapped_column(Float, default=0.0)  # 价格分
    service_score: Mapped[float] = mapped_column(Float, default=0.0)  # 服务分
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

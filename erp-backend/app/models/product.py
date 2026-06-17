"""商品/物料模型"""
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductCategory(Base):
    """产品分类"""
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    bullwhip_threshold: Mapped[float] = mapped_column(Float, default=1.5, server_default="1.5")  # 牛鞭效应预警阈值
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Product(Base):
    """产品/物料"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    specification: Mapped[str] = mapped_column(String(500), default="")
    unit: Mapped[str] = mapped_column(String(20), default="个")           # 单位
    purchase_price: Mapped[float] = mapped_column(Float, default=0.0)     # 采购价
    sale_price: Mapped[float] = mapped_column(Float, default=0.0)         # 销售价
    cost_price: Mapped[float] = mapped_column(Float, default=0.0)         # 成本价
    min_stock: Mapped[float] = mapped_column(Float, default=0.0)          # 最低库存预警
    max_stock: Mapped[float] = mapped_column(Float, default=0.0)          # 最高库存预警
    lead_time_override: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 产品级交期（天），覆盖供应商交期
    box_qty: Mapped[int] = mapped_column(Integer, default=1)              # 包装数量，建议量对齐整数倍
    barcode: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    weather_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # 是否受天气影响
    weather_type: Mapped[list | None] = mapped_column(JSON, nullable=True)  # 影响类型: ["hot","rain"] 等
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

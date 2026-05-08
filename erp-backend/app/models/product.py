"""商品/物料模型"""
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductCategory(Base):
    """产品分类"""
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
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
    barcode: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

"""促销活动模型 — Prophet 回归量数据源"""
from datetime import date, datetime
from sqlalchemy import String, Float, Integer, Boolean, Date, Text, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Promotion(Base):
    """促销活动"""
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200))                         # 活动名：双11/618/店庆
    start_date: Mapped[date] = mapped_column(Date)                         # 开始日期
    end_date: Mapped[date] = mapped_column(Date)                           # 结束日期
    promotion_type: Mapped[str] = mapped_column(String(20), default="discount")  # discount/bundle/flash/clearance
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)        # 折扣百分比 (0-100)
    product_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)  # 受影响产品ID列表
    expected_lift_pct: Mapped[float] = mapped_column(Float, default=0.0)   # 预期销量提升百分比
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

"""AI 决策记录模型"""
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIDecisionRecord(Base):
    """AI 决策记录"""
    __tablename__ = "ai_decision_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    decision_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # stock_alert / purchase_suggest / sales_forecast / supplier_evaluate
    title: Mapped[str] = mapped_column(String(200))
    input_data: Mapped[str] = mapped_column(Text, default="")       # 输入数据（JSON）
    output_data: Mapped[str] = mapped_column(Text, default="")      # AI 输出（JSON）
    summary: Mapped[str] = mapped_column(Text, default="")          # 中文总结
    confidence: Mapped[float] = mapped_column(Float, default=0.0)   # 置信度
    related_id: Mapped[int] = mapped_column(Integer, default=0)     # 关联业务ID
    is_applied: Mapped[bool] = mapped_column(default=False)         # 是否被采纳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

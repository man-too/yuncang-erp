"""用户模型"""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.OPERATOR
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

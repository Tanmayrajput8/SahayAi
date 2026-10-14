import enum
from typing import Optional
from sqlalchemy import String, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class UserRole(str, enum.Enum):
    CITIZEN = "citizen"
    DISPATCHER = "dispatcher"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


class User(Base, TimestampMixin):
    """User account entity for Citizens, Dispatchers, and Supervisors."""
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.DISPATCHER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    badge_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.case import SeverityLevel


class SLATracking(Base, TimestampMixin):
    """SLA timer and response-time tracking per emergency case."""
    __tablename__ = "sla_tracking"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    severity_level: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel), nullable=False)
    target_seconds: Mapped[int] = mapped_column(Integer, default=480, nullable=False) # e.g., 8 min (480s) for Critical, 15m for High
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_breached: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_warning: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    warning_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    breached_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    breach_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    case = relationship("Case", back_populates="sla_tracking")

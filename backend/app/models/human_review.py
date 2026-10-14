import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class ReviewStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    OVERRIDDEN = "OVERRIDDEN"


class HumanReview(Base, TimestampMixin):
    """Human-in-the-loop review log and dispatcher overrides for low-confidence or high-risk cases."""
    __tablename__ = "human_reviews"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    dispatcher_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    review_status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False, index=True)
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False)   # e.g., "Confidence 0.62 below 0.75 threshold"
    original_decision: Mapped[dict] = mapped_column(JSON, default=dict) # Snapshot of AI recommendation
    final_decision: Mapped[dict] = mapped_column(JSON, default=dict)    # Final action after human confirmation/override
    dispatcher_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    case = relationship("Case", back_populates="human_reviews")
    dispatcher = relationship("User")

from typing import Optional
from sqlalchemy import String, Float, Boolean, Enum, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.case import SeverityLevel


class FairnessRecord(Base, TimestampMixin):
    """Fairness benchmark metrics evaluating model performance across language/dialect groups."""
    __tablename__ = "fairness_records"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    language_group: Mapped[str] = mapped_column(String(32), nullable=False, index=True) # English, Hindi, Marathi, Code-mixed
    dialect_type: Mapped[str] = mapped_column(String(64), default="standard")          # Standard, Puneri Marathi, Mumbai Tapori, Hinglish
    predicted_severity: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel), nullable=False)
    verified_severity: Mapped[Optional[SeverityLevel]] = mapped_column(Enum(SeverityLevel), nullable=True)
    is_disparity_flagged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_accuracy: Mapped[float] = mapped_column(Float, default=1.0)               # Accuracy score for field extraction

    # Relationships
    case = relationship("Case", back_populates="fairness_records")

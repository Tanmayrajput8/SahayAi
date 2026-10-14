import enum
from typing import Optional, List
from sqlalchemy import String, Float, Text, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class VerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTING = "CONFLICTING"


class VerificationResult(Base, TimestampMixin):
    """RAG-based protocol and clinical verification evidence for an emergency case."""
    __tablename__ = "verification_results"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    protocol_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g., "CARD-01"
    status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus), default=VerificationStatus.VERIFIED, nullable=False)
    verified_fields: Mapped[list] = mapped_column(JSON, default=list)       # e.g., ["symptoms", "severity"]
    conflicting_fields: Mapped[list] = mapped_column(JSON, default=list)    # e.g., ["ambulance_type"]
    rag_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # Protocol excerpt / cited medical guidance
    verification_score: Mapped[float] = mapped_column(Float, default=1.0)

    # Relationships
    case = relationship("Case", back_populates="verification_results")

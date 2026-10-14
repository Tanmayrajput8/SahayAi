from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Float, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class ExtractedInfo(Base, TimestampMixin):
    """Structured information extracted by AI from the emergency call/text."""
    __tablename__ = "extracted_info"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    emergency_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # Cardiac, Road Accident, Burns, etc.
    symptoms: Mapped[list] = mapped_column(JSON, default=list)                         # ["chest pain", "shortness of breath"]
    extracted_location_text: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # Raw location string mentioned by caller
    patient_count: Mapped[int] = mapped_column(Integer, default=1)
    conscious_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)          # conscious, unconscious, semi-conscious
    breathing_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)          # normal, shallow, gasping, stopped
    raw_llm_output: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationships
    case = relationship("Case", back_populates="extracted_info")

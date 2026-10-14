from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class ResourceMatch(Base, TimestampMixin):
    """Resource match pairing an optimal ambulance and specialty hospital to an emergency case."""
    __tablename__ = "resource_matches"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    ambulance_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("ambulances.id", ondelete="SET NULL"), nullable=True, index=True)
    hospital_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("hospitals.id", ondelete="SET NULL"), nullable=True, index=True)
    
    ambulance_distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    ambulance_eta_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    hospital_distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    selection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_dispatched: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    case = relationship("Case", back_populates="resource_matches")
    ambulance = relationship("Ambulance", back_populates="resource_matches")
    hospital = relationship("Hospital", back_populates="resource_matches")

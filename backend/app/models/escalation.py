import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class EscalationLevel(str, enum.Enum):
    SUPERVISOR_ALERT = "SUPERVISOR_ALERT"
    PRIORITY_BOOST = "PRIORITY_BOOST"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class EscalationTrigger(str, enum.Enum):
    SYSTEM_SLA = "SYSTEM_SLA"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    DISPATCHER = "DISPATCHER"
    NO_AMBULANCE_AVAILABLE = "NO_AMBULANCE_AVAILABLE"


class EscalationEvent(Base, TimestampMixin):
    """Escalation records triggered by SLA breaches, resource shortages, or low confidence."""
    __tablename__ = "escalation_events"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    escalation_level: Mapped[EscalationLevel] = mapped_column(Enum(EscalationLevel), default=EscalationLevel.SUPERVISOR_ALERT, nullable=False, index=True)
    triggered_by: Mapped[EscalationTrigger] = mapped_column(Enum(EscalationTrigger), default=EscalationTrigger.SYSTEM_SLA, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    case = relationship("Case", back_populates="escalation_events")

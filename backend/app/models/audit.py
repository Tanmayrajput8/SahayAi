import enum
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class AuditStage(str, enum.Enum):
    INTAKE = "INTAKE"
    AI_EXTRACTION = "AI_EXTRACTION"
    SEVERITY_RECOMMENDATION = "SEVERITY_RECOMMENDATION"
    GEOCODING = "GEOCODING"
    RESOURCE_MATCHING = "RESOURCE_MATCHING"
    DUPLICATE_CHECK = "DUPLICATE_CHECK"
    RAG_VERIFICATION = "RAG_VERIFICATION"
    CONFIDENCE_SCORING = "CONFIDENCE_SCORING"
    DISPATCH = "DISPATCH"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SLA_ESCALATION = "SLA_ESCALATION"


class AuditLog(Base, TimestampMixin):
    """Immutable Audit Event Log for every decision stage in the pipeline."""
    __tablename__ = "audit_logs"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    stage: Mapped[AuditStage] = mapped_column(Enum(AuditStage), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), default="AI_ENGINE", nullable=False)  # "AI_ENGINE", "DISPATCHER_<ID>", "SYSTEM_MONITOR"
    action: Mapped[str] = mapped_column(String(128), nullable=False)                    # e.g., "SEVERITY_CALCULATED", "DISPATCH_OVERRIDDEN"
    details: Mapped[dict] = mapped_column(JSON, default=dict)                           # Payload snapshot or decision delta
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)                        # Latency of this processing step

    # Relationships
    case = relationship("Case", back_populates="audit_logs")

    @property
    def incident_id(self) -> str:
        return self.case_id

    @incident_id.setter
    def incident_id(self, val: str):
        self.case_id = val

    @property
    def incident(self):
        return self.case

    @incident.setter
    def incident(self, val):
        self.case = val

import enum
from typing import Optional
from sqlalchemy import String, Text, Enum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class SeverityLevel(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class AmbulanceType(str, enum.Enum):
    ALS = "ALS"
    BLS = "BLS"
    UNKNOWN = "UNKNOWN"


class InputModality(str, enum.Enum):
    TEXT = "text"
    VOICE = "voice"
    AUDIO = "audio"


class CaseStatus(str, enum.Enum):
    PENDING = "PENDING"
    TRIAGED = "TRIAGED"
    UNDER_REVIEW = "UNDER_REVIEW"
    DISPATCHED = "DISPATCHED"
    ARRIVED = "ARRIVED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    DUPLICATE = "DUPLICATE"


class Case(Base, TimestampMixin):
    """Primary Emergency Case Record."""
    __tablename__ = "cases"

    caller_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    modality: Mapped[str] = mapped_column(String(32), default=InputModality.TEXT.value, nullable=False)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    language: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)  # english, hindi, marathi, code-mixed
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.PENDING, nullable=False, index=True)
    priority: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel), default=SeverityLevel.MODERATE, nullable=False, index=True)

    @property
    def raw_input(self) -> str:
        return (self.raw_text)

    # Relationships
    extracted_info = relationship("ExtractedInfo", back_populates="case", uselist=False, cascade="all, delete-orphan", single_parent=True)
    location = relationship("Location", back_populates="case", uselist=False, cascade="all, delete-orphan", single_parent=True)

    resource_matches = relationship("ResourceMatch", back_populates="case", cascade="all, delete-orphan")
    ai_decisions = relationship("AIDecision", back_populates="case", cascade="all, delete-orphan")
    verification_results = relationship("VerificationResult", back_populates="case", cascade="all, delete-orphan")
    human_reviews = relationship("HumanReview", back_populates="case", cascade="all, delete-orphan")
    sla_tracking = relationship("SLATracking", back_populates="case", uselist=False, cascade="all, delete-orphan")
    escalation_events = relationship("EscalationEvent", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case", cascade="all, delete-orphan")
    fairness_records = relationship("FairnessRecord", back_populates="case", cascade="all, delete-orphan")

    # Duplicate relationships
    duplicate_associations = relationship(
        "DuplicateRelationship",
        foreign_keys="[DuplicateRelationship.primary_case_id]",
        back_populates="primary_case",
        cascade="all, delete-orphan",
    )
    duplicate_of = relationship(
        "DuplicateRelationship",
        foreign_keys="[DuplicateRelationship.duplicate_case_id]",
        back_populates="duplicate_case",
        cascade="all, delete-orphan",
    )


# Aliases for backward compatibility
Incident = Case
IncidentStatus = CaseStatus

from typing import Optional, List
from sqlalchemy import String, Text, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.incident import SeverityLevel, AmbulanceType


class EmergencyProtocol(Base, TimestampMixin):
    """Clinical triage guidelines for RAG verification and explainability."""
    __tablename__ = "emergency_protocols"

    protocol_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False) # e.g. "CARD-01", "TRAUMA-01"
    category: Mapped[str] = mapped_column(String(64), nullable=False)                   # Cardiac, Trauma, Respiratory, etc.
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Clinical Triage Rules
    severity_default: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel), default=SeverityLevel.MODERATE, nullable=False)
    required_ambulance_type: Mapped[AmbulanceType] = mapped_column(Enum(AmbulanceType), default=AmbulanceType.BLS, nullable=False)
    key_symptoms: Mapped[list] = mapped_column(JSON, default=list)            # Keywords and symptom patterns
    mandatory_equipment: Mapped[list] = mapped_column(JSON, default=list)     # ["Defibrillator", "Oxygen", "Ventilator"]
    first_aid_guidance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # Instructions for the caller while ambulance is en route

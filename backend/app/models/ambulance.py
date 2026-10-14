import enum
from typing import Optional, List, Any
from sqlalchemy import String, Float, Enum, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.case import AmbulanceType


class AmbulanceStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    DISPATCHED = "DISPATCHED"
    BUSY = "BUSY"
    MAINTENANCE = "MAINTENANCE"


class Ambulance(Base, TimestampMixin):
    """Simulated Ambulance Fleet Entity."""
    __tablename__ = "ambulances"

    vehicle_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    ambulance_type: Mapped[AmbulanceType] = mapped_column(Enum(AmbulanceType), nullable=False, default=AmbulanceType.BLS, index=True)
    base_station: Mapped[str] = mapped_column(String(128), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[AmbulanceStatus] = mapped_column(Enum(AmbulanceStatus), default=AmbulanceStatus.AVAILABLE, nullable=False, index=True)
    equipment: Mapped[list] = mapped_column(JSON, default=list)  # e.g., ["Oxygen", "Defibrillator", "Ventilator", "ECG"]
    contact_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    driver_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    resource_matches = relationship("ResourceMatch", back_populates="ambulance")

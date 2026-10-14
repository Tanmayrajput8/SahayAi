from typing import Optional, List, Any
from sqlalchemy import String, Integer, Float, Boolean, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class Hospital(Base, TimestampMixin):
    """Simulated Hospital / Emergency Resource Facility."""
    __tablename__ = "hospitals"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(256), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Capacity & Capabilities
    total_beds: Mapped[int] = mapped_column(Integer, default=50)
    available_beds: Mapped[int] = mapped_column(Integer, default=20)
    available_icu_beds: Mapped[int] = mapped_column(Integer, default=5)
    has_trauma_center: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_cardiac_care: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_burn_unit: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_pediatric_icu: Mapped[bool] = mapped_column(Boolean, default=False)
    specializations: Mapped[list] = mapped_column(JSON, default=list)  # e.g., ["TRAUMA", "CARDIAC", "NEUROLOGY"]

    contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    resource_matches = relationship("ResourceMatch", back_populates="hospital")

import enum
from typing import Optional
from sqlalchemy import String, Float, Boolean, Text, ForeignKey, TypeDecorator
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class GeocodingStatus(str, enum.Enum):
    SUCCESS = "success"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"

    def __eq__(self, other):
        if isinstance(other, (str, enum.Enum)):
            val = getattr(other, "value", other)
            return self.value.lower() == str(val).lower()
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.value.lower())


class GeocodingStatusType(TypeDecorator):
    """SQLAlchemy TypeDecorator for GeocodingStatus enum with case-insensitive string binding."""
    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "value"):
            return str(value.value).lower()
        return str(value).lower()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        val = str(value).lower()
        try:
            return GeocodingStatus(val)
        except ValueError:
            return GeocodingStatus.SUCCESS


class Location(Base, TimestampMixin):
    """Geocoded location and spatial metadata for emergency cases."""
    __tablename__ = "locations"

    case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    raw_query: Mapped[str] = mapped_column(String(256), nullable=False)
    formatted_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), default="Pune", nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(64), default="Maharashtra", nullable=True)
    geocoding_provider: Mapped[str] = mapped_column(String(32), default="nominatim")  # nominatim, mock, manual
    status: Mapped[GeocodingStatus] = mapped_column(GeocodingStatusType, default=GeocodingStatus.SUCCESS, nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @property
    def location_text(self) -> str:
        return str(self.raw_query or "")

    @location_text.setter
    def location_text(self, val: str):
        setattr(self, "raw_query", val)

    @property
    def provider(self) -> str:
        return str(self.geocoding_provider or "")

    @provider.setter
    def provider(self, val: str):
        setattr(self, "geocoding_provider", val)

    # Relationships
    case = relationship("Case", back_populates="location")

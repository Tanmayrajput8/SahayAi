from sqlalchemy import String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base
from app.models.base import TimestampMixin


class DuplicateRelationship(Base, TimestampMixin):
    """Pairwise duplicate incident link based on semantic, spatial, temporal, and clinical similarity."""
    __tablename__ = "duplicate_relationships"

    primary_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    duplicate_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    
    semantic_similarity: Mapped[float] = mapped_column(Float, default=0.0)      # Vector / text similarity (0-1)
    geographic_distance_km: Mapped[float] = mapped_column(Float, default=0.0)   # Distance in km
    temporal_diff_minutes: Mapped[float] = mapped_column(Float, default=0.0)    # Time difference in minutes
    emergency_type_similarity: Mapped[float] = mapped_column(Float, default=0.0) # Clinical taxonomy similarity (0-1)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)       # Combined duplicate score
    is_confirmed_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    detection_method: Mapped[str] = mapped_column(String(64), default="WEIGHTED_MULTISIGNAL")

    # Relationships
    primary_case = relationship("Case", foreign_keys=[primary_case_id], back_populates="duplicate_associations")
    duplicate_case = relationship("Case", foreign_keys=[duplicate_case_id], back_populates="duplicate_of")

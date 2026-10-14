"""Schemas for geocoding operations and spatial intelligence."""
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.location import GeocodingStatus


class GeocodingCandidate(BaseModel):
    """Candidate geographic location returned by geocoding API."""
    display_name: str
    latitude: float
    longitude: float
    importance: float = 0.5
    place_id: Optional[str] = None
    type: Optional[str] = None


class GeocodingResult(BaseModel):
    """
    Standardized geocoding result.
    Statuses: 'success', 'ambiguous', 'failed'.
    """
    query: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: Optional[str] = None
    city: Optional[str] = "Pune"
    state: Optional[str] = "Maharashtra"
    provider: str = "nominatim"
    status: GeocodingStatus = GeocodingStatus.SUCCESS
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_verified: bool = False
    candidates: List[GeocodingCandidate] = Field(default_factory=list)
    error_message: Optional[str] = None

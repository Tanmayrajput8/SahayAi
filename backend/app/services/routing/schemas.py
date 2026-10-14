"""Schemas for routing calculations and external navigation providers."""
from typing import Optional
from pydantic import BaseModel, Field


class RouteResult(BaseModel):
    """
    Standardized routing response between origin and destination coordinates.
    
    Guarantees:
    - Never claims live traffic information unless explicitly sourced from a live telemetry provider.
    - Captures whether a lightweight mathematical fallback was utilized due to API failure.
    """
    distance_km: float = Field(..., description="Driving route distance in kilometers")
    duration_minutes: float = Field(..., description="Estimated travel time in minutes")
    provider: str = Field(..., description="Routing provider identifier (e.g., 'osrm', 'openrouteservice', 'haversine_fallback')")
    has_live_traffic: bool = Field(
        default=False,
        description="Whether live telemetry traffic data was incorporated. Must remain False for static/graph routing.",
    )
    is_fallback: bool = Field(
        default=False,
        description="True if external API failed and mathematical fallback was employed.",
    )
    fallback_reason: Optional[str] = Field(
        default=None,
        description="Reason why the lightweight fallback was triggered if applicable.",
    )
    traffic_disclaimer: str = Field(
        default="Static road network estimate; live traffic conditions are not included.",
        description="Explicit user-facing statement regarding traffic data availability.",
    )

"""Lightweight Mathematical Fallback Routing Provider.

Calculates distance using the spherical Haversine formula adjusted by an
urban road network tortuosity factor (1.35x), and estimates transit ETA
assuming an average emergency vehicle urban response velocity of 35 km/h.

Used when external routing APIs (OSRM / OpenRouteService) fail, time out,
or hit rate limits, guaranteeing zero dependency on a local routing engine.
"""
import math
import logging
from typing import Optional
from app.services.routing.base import RoutingProvider
from app.services.routing.schemas import RouteResult

logger = logging.getLogger(__name__)

# Mean Earth radius in kilometers
EARTH_RADIUS_KM: float = 6371.0

# Urban road network tortuosity coefficient (ratio of road travel distance to straight-line Euclidean distance)
URBAN_TORTUOSITY_FACTOR: float = 1.35

# Average emergency response vehicle velocity in Indian urban traffic corridors (km/h)
AVERAGE_EMERGENCY_SPEED_KMH: float = 35.0


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth's surface
    using the Haversine formula.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c


class HaversineFallbackRouter(RoutingProvider):
    """
    Clearly documented lightweight routing fallback.
    Executes entirely in-memory without network calls or local routing engines.
    """

    def __init__(
        self,
        tortuosity_factor: float = URBAN_TORTUOSITY_FACTOR,
        speed_kmh: float = AVERAGE_EMERGENCY_SPEED_KMH,
    ):
        self.tortuosity_factor = tortuosity_factor
        self.speed_kmh = speed_kmh

    @property
    def provider_name(self) -> str:
        return "haversine_fallback"

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        fallback_reason: Optional[str] = None,
    ) -> RouteResult:
        """
        Estimate road distance and transit duration using Haversine calculation.
        """
        # Validate coordinate bounds
        if not (-90.0 <= origin_lat <= 90.0 and -180.0 <= origin_lon <= 180.0):
            raise ValueError(f"Invalid origin coordinates: ({origin_lat}, {origin_lon})")
        if not (-90.0 <= dest_lat <= 90.0 and -180.0 <= dest_lon <= 180.0):
            raise ValueError(f"Invalid destination coordinates: ({dest_lat}, {dest_lon})")

        straight_line_km = haversine_distance_km(origin_lat, origin_lon, dest_lat, dest_lon)
        # Apply urban road network tortuosity
        road_distance_km = max(0.1, straight_line_km * self.tortuosity_factor)

        # Estimate duration in minutes: (distance / speed) * 60
        duration_minutes = max(1.0, (road_distance_km / self.speed_kmh) * 60.0)

        reason = fallback_reason or "Routing calculated via mathematical fallback (Haversine + urban tortuosity)."

        return RouteResult(
            distance_km=round(road_distance_km, 2),
            duration_minutes=round(duration_minutes, 1),
            provider=self.provider_name,
            has_live_traffic=False,
            is_fallback=True,
            fallback_reason=reason,
            traffic_disclaimer=(
                "LIGHTWEIGHT FALLBACK: Estimated using Haversine great-circle distance "
                f"with {self.tortuosity_factor:.2f}x urban road tortuosity factor and "
                f"{self.speed_kmh:.1f} km/h emergency transit velocity. "
                "Live traffic telemetry is NOT available."
            ),
        )

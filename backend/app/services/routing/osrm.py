"""External OSRM (Open Source Routing Machine) REST API Provider.

Connects to the public OSRM routing service over HTTPS.
Does NOT install or run any local routing engine.
Includes retries, timeout handling, and automatic fail-safe fallback to
Haversine mathematical estimation if the external API is unreachable.
"""
import logging
import time
from typing import Optional
import httpx

from app.services.routing.base import RoutingProvider
from app.services.routing.schemas import RouteResult
from app.services.routing.fallback import HaversineFallbackRouter

logger = logging.getLogger(__name__)


class OSRMRoutingProvider(RoutingProvider):
    """
    External routing client connecting to the public OSRM REST endpoint.
    Public OSRM computes distances based on OpenStreetMap static road topology;
    it does NOT incorporate real-time GPS traffic telemetry.
    """

    def __init__(
        self,
        base_url: str = "https://router.project-osrm.org/route/v1/driving",
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self._fallback = HaversineFallbackRouter()

    @property
    def provider_name(self) -> str:
        return "osrm"

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> RouteResult:
        """
        Request route distance and duration from the external OSRM service.
        Note: OSRM URL format expects coordinates as {longitude},{latitude}.
        """
        # Formulate coordinate segment: lon,lat;lon,lat
        coords = f"{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}"
        url = f"{self.base_url}/{coords}"
        params = {"overview": "false", "steps": "false"}
        headers = {
            "User-Agent": "SahayAI-Emergency-Dispatch/0.1.0 (emergency-routing@sahayai.internal)",
            "Accept": "application/json",
        }

        last_error: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, params=params, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == "Ok" and data.get("routes"):
                        route = data["routes"][0]
                        # OSRM returns distance in meters, duration in seconds
                        distance_meters = float(route.get("distance", 0.0))
                        duration_seconds = float(route.get("duration", 0.0))

                        distance_km = round(distance_meters / 1000.0, 2)
                        duration_minutes = round(max(1.0, duration_seconds / 60.0), 1)

                        return RouteResult(
                            distance_km=distance_km,
                            duration_minutes=duration_minutes,
                            provider=self.provider_name,
                            has_live_traffic=False,
                            is_fallback=False,
                            fallback_reason=None,
                            traffic_disclaimer=(
                                "Calculated via OSRM public static road network graph. "
                                "Real-time traffic telemetry is NOT provided by this API."
                            ),
                        )
                    else:
                        last_error = f"OSRM non-OK response: {data.get('code')}"
                else:
                    last_error = f"OSRM HTTP {resp.status_code}: {resp.text[:120]}"

            except httpx.TimeoutException:
                last_error = f"OSRM request timed out after {self.timeout}s"
            except httpx.RequestError as exc:
                last_error = f"OSRM network error: {str(exc)}"
            except Exception as exc:
                last_error = f"OSRM parsing error: {str(exc)}"

            if attempt < self.max_retries:
                time.sleep(0.3 * (attempt + 1))

        # External API failed; trigger lightweight fallback
        logger.warning(
            "OSRM routing failed after %d attempts (%s). Triggering Haversine fallback.",
            self.max_retries + 1,
            last_error,
        )
        return self._fallback.calculate_route(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            fallback_reason=f"OSRM routing service unavailable ({last_error}). Applied mathematical fallback.",
        )

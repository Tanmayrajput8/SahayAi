"""External OpenRouteService (ORS) REST API Provider.

Connects to the OpenRouteService directions API over HTTPS.
Does NOT install or run any local routing engine.
Includes retries, timeout handling, and automatic fail-safe fallback to
Haversine mathematical estimation if the external API is unreachable or key is unset.
"""
import logging
import time
from typing import Optional
import httpx

from app.services.routing.base import RoutingProvider
from app.services.routing.schemas import RouteResult
from app.services.routing.fallback import HaversineFallbackRouter

logger = logging.getLogger(__name__)


class OpenRouteServiceProvider(RoutingProvider):
    """
    External routing client connecting to the OpenRouteService directions API.
    Does NOT claim live traffic data unless live telemetry is supplied by the tier.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openrouteservice.org/v2/directions/driving-car",
        timeout_seconds: float = 5.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self._fallback = HaversineFallbackRouter()

    @property
    def provider_name(self) -> str:
        return "openrouteservice"

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> RouteResult:
        """
        Request driving directions and ETA from OpenRouteService.
        """
        if not self.api_key:
            return self._fallback.calculate_route(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                fallback_reason="OpenRouteService API key not configured. Applied mathematical fallback.",
            )

        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, application/geo+json",
        }
        payload = {
            "coordinates": [[origin_lon, origin_lat], [dest_lon, dest_lat]],
        }

        last_error: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(self.base_url, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    routes = data.get("routes", [])
                    if routes:
                        summary = routes[0].get("summary", {})
                        distance_meters = float(summary.get("distance", 0.0))
                        duration_seconds = float(summary.get("duration", 0.0))

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
                                "Calculated via OpenRouteService directions API. "
                                "Real-time traffic telemetry is NOT provided by this endpoint."
                            ),
                        )
                    else:
                        last_error = "OpenRouteService returned 0 routes in response"
                else:
                    last_error = f"OpenRouteService HTTP {resp.status_code}: {resp.text[:120]}"

            except httpx.TimeoutException:
                last_error = f"OpenRouteService request timed out after {self.timeout}s"
            except httpx.RequestError as exc:
                last_error = f"OpenRouteService network error: {str(exc)}"
            except Exception as exc:
                last_error = f"OpenRouteService parsing error: {str(exc)}"

            if attempt < self.max_retries:
                time.sleep(0.3 * (attempt + 1))

        logger.warning(
            "OpenRouteService failed after %d attempts (%s). Triggering Haversine fallback.",
            self.max_retries + 1,
            last_error,
        )
        return self._fallback.calculate_route(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            fallback_reason=f"OpenRouteService unavailable ({last_error}). Applied mathematical fallback.",
        )

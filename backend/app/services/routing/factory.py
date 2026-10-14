"""Factory for obtaining routing providers based on configuration or runtime selection."""
from typing import Optional
from app.core.config import settings
from app.services.routing.base import RoutingProvider
from app.services.routing.osrm import OSRMRoutingProvider
from app.services.routing.openrouteservice import OpenRouteServiceProvider
from app.services.routing.fallback import HaversineFallbackRouter


def get_routing_provider(name: Optional[str] = None) -> RoutingProvider:
    """
    Get the configured routing provider.
    
    Supported providers:
    - 'osrm': Public OSRM REST API (default) with automatic fallback.
    - 'openrouteservice' / 'ors': OpenRouteService REST API with automatic fallback.
    - 'fallback' / 'haversine': Deterministic in-memory Haversine router.
    """
    provider_name = (name or settings.ROUTING_PROVIDER or "osrm").lower()

    if provider_name == "osrm":
        return OSRMRoutingProvider(
            base_url=settings.OSRM_BASE_URL,
            timeout_seconds=settings.ROUTING_TIMEOUT_SECONDS,
            max_retries=settings.ROUTING_MAX_RETRIES,
        )
    elif provider_name in ("openrouteservice", "ors"):
        return OpenRouteServiceProvider(
            api_key=settings.OPENROUTESERVICE_API_KEY,
            base_url=settings.OPENROUTESERVICE_BASE_URL,
            timeout_seconds=settings.ROUTING_TIMEOUT_SECONDS,
            max_retries=settings.ROUTING_MAX_RETRIES,
        )
    elif provider_name in ("fallback", "haversine", "mock"):
        return HaversineFallbackRouter()
    else:
        # Default safe fallback
        return OSRMRoutingProvider(
            base_url=settings.OSRM_BASE_URL,
            timeout_seconds=settings.ROUTING_TIMEOUT_SECONDS,
            max_retries=settings.ROUTING_MAX_RETRIES,
        )

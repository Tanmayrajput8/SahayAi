"""Routing Provider Module for Emergency Dispatch."""
from app.services.routing.schemas import RouteResult
from app.services.routing.base import RoutingProvider
from app.services.routing.fallback import HaversineFallbackRouter, haversine_distance_km
from app.services.routing.osrm import OSRMRoutingProvider
from app.services.routing.openrouteservice import OpenRouteServiceProvider
from app.services.routing.factory import get_routing_provider

__all__ = [
    "RouteResult",
    "RoutingProvider",
    "HaversineFallbackRouter",
    "haversine_distance_km",
    "OSRMRoutingProvider",
    "OpenRouteServiceProvider",
    "get_routing_provider",
]

"""Abstract Base Class for Routing providers."""
from abc import ABC, abstractmethod
from app.services.routing.schemas import RouteResult


class RoutingProvider(ABC):
    """
    Abstract interface for routing distance and ETA calculations.
    All routing operations must communicate through this abstraction.
    Does NOT require a local routing engine installation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier name of the provider."""
        pass

    @abstractmethod
    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> RouteResult:
        """
        Calculate road distance (km) and estimated travel duration (minutes)
        from origin to destination coordinates.
        
        Must handle timeouts, network errors, and API limits without raising
        unhandled exceptions, falling back seamlessly to lightweight estimation.
        """
        pass

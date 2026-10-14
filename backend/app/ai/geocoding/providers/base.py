"""Abstract Base Class for Geocoding providers."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from app.ai.geocoding.schemas import GeocodingResult


class GeocodingProvider(ABC):
    """
    Abstract Base Class for external geocoding providers.
    All location geocoding must interact through this abstraction.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the geocoding provider (e.g. 'nominatim', 'mock')."""
        pass

    @abstractmethod
    def geocode(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GeocodingResult:
        """
        Geocode a location text string into latitude, longitude, and spatial metadata.
        Must handle timeouts, retries, ambiguity, and failure modes without raising
        unhandled exceptions that would reject the emergency.
        """
        pass

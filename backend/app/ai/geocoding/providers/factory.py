"""Factory for Geocoding provider instantiation."""
import logging
from typing import Optional

from app.core.config import settings
from app.ai.geocoding.providers.base import GeocodingProvider
from app.ai.geocoding.providers.nominatim import NominatimGeocodingProvider
from app.ai.geocoding.providers.mock import MockGeocodingProvider

logger = logging.getLogger(__name__)


def get_geocoding_provider(provider_override: Optional[str] = None) -> GeocodingProvider:
    """
    Retrieve configured GeocodingProvider.
    Supports 'nominatim' (OpenStreetMap REST API) and 'mock'.
    """
    choice = (provider_override or getattr(settings, "GEOCODING_PROVIDER", "mock")).strip().lower()

    if choice == "nominatim":
        base_url = getattr(settings, "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org/search")
        timeout = getattr(settings, "GEOCODING_TIMEOUT_SECONDS", 5.0)
        retries = getattr(settings, "GEOCODING_MAX_RETRIES", 2)
        user_agent = getattr(settings, "NOMINATIM_USER_AGENT", "SahayAI-Emergency/1.0")
        return NominatimGeocodingProvider(
            base_url=base_url,
            timeout=timeout,
            max_retries=retries,
            user_agent=user_agent,
        )

    return MockGeocodingProvider()

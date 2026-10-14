"""Geocoding package exports."""
from app.ai.geocoding.schemas import GeocodingResult, GeocodingCandidate
from app.ai.geocoding.providers.base import GeocodingProvider
from app.ai.geocoding.providers.nominatim import NominatimGeocodingProvider
from app.ai.geocoding.providers.mock import MockGeocodingProvider
from app.ai.geocoding.providers.factory import get_geocoding_provider
from app.ai.geocoding.service import process_case_geocoding, manually_verify_case_location

__all__ = [
    "GeocodingResult",
    "GeocodingCandidate",
    "GeocodingProvider",
    "NominatimGeocodingProvider",
    "MockGeocodingProvider",
    "get_geocoding_provider",
    "process_case_geocoding",
    "manually_verify_case_location",
]

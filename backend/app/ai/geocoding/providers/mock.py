"""Mock Geocoding Provider for testing, local offline development, and CI."""
import logging
from typing import Optional, Dict, Any, List

from app.models.location import GeocodingStatus
from app.ai.geocoding.schemas import GeocodingResult, GeocodingCandidate
from app.ai.geocoding.providers.base import GeocodingProvider

logger = logging.getLogger(__name__)

# Known geographic coordinates in Pune & Mumbai for offline deterministic evaluation
KNOWN_SPATIAL_DIRECTORY = {
    "marine drive": (18.9438, 72.8232, "Marine Drive, Netaji Subhash Chandra Bose Road, Mumbai, Maharashtra, 400020, India"),
    "dadar station": (19.0178, 72.8478, "Dadar Western Railway Station, Senapati Bapat Marg, Mumbai, Maharashtra, 400028, India"),
    "dadar": (19.0178, 72.8478, "Dadar, Mumbai, Maharashtra, India"),
    "swargate": (18.5018, 73.8586, "Swargate Bus Stand, Shivaji Road, Pune, Maharashtra, 411042, India"),
    "andheri station": (19.1197, 72.8464, "Andheri Railway Station, Station Road, Mumbai, Maharashtra, 400058, India"),
    "andheri": (19.1197, 72.8464, "Andheri, Mumbai, Maharashtra, India"),
    "kurla signal": (19.0688, 72.8797, "Kurla Signal, LBS Marg, Kurla West, Mumbai, Maharashtra, 400070, India"),
    "kurla": (19.0688, 72.8797, "Kurla, Mumbai, Maharashtra, India"),
    "kothrud": (18.5074, 73.8077, "Kothrud, Pune, Maharashtra, 411038, India"),
    "bandra west": (19.0596, 72.8295, "Bandra West, Mumbai, Maharashtra, 400050, India"),
    "bandra": (19.0596, 72.8295, "Bandra, Mumbai, Maharashtra, India"),
    "shivajinagar": (18.5314, 73.8446, "Shivajinagar, Pune, Maharashtra, 411005, India"),
    "fc road": (18.5255, 73.8415, "Fergusson College Road, Shivajinagar, Pune, Maharashtra, 411004, India"),
    "deccan": (18.5167, 73.8417, "Deccan Gymkhana, Pune, Maharashtra, 411004, India"),
    "pune": (18.5204, 73.8567, "Pune, Maharashtra, India"),
    "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra, India"),
    "अंधेरी": (19.1197, 72.8464, "अंधेरी स्टेशन (Andheri Station), Mumbai, Maharashtra, India"),
    "दादर": (19.0178, 72.8478, "दादर स्टेशन (Dadar Station), Mumbai, Maharashtra, India"),
    "कुर्ला": (19.0688, 72.8797, "कुर्ला (Kurla), Mumbai, Maharashtra, India"),
}

# Generic queries that exist in dozens of locations and are inherently ambiguous
AMBIGUOUS_PATTERNS = [
    "mg road", "m.g. road", "station", "railway station", "bus stand",
    "market", "main road", "signal", "depot", "highway", "junction",
]


class MockGeocodingProvider(GeocodingProvider):
    """
    Deterministic Mock Geocoding Provider.
    Accurately simulates:
    - Valid location queries with coordinates and formatted addresses (success)
    - Ambiguous multi-point queries (ambiguous)
    - Unresolvable, invalid, or empty location queries (failed)
    - Timeout and service failure simulations
    """

    def __init__(
        self,
        simulate_timeout: bool = False,
        simulate_error: bool = False,
        simulate_ambiguous: bool = False,
        simulate_failed: bool = False,
    ):
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.simulate_ambiguous = simulate_ambiguous
        self.simulate_failed = simulate_failed

    @property
    def provider_name(self) -> str:
        return "mock_geocoder"

    def geocode(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GeocodingResult:
        """Simulate geocoding resolution."""
        clean_query = (query or "").strip()
        lower = clean_query.lower()

        # 1. Error / Timeout simulation
        if self.simulate_timeout:
            return GeocodingResult(
                query=clean_query,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message="Simulated Geocoding API timed out after 5.0s.",
            )

        if self.simulate_error:
            return GeocodingResult(
                query=clean_query,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message="Simulated Upstream Geocoding API 500 Internal Error.",
            )

        # 2. Empty or explicit failed simulation
        if not clean_query or self.simulate_failed or "invalid" in lower or "nonexistent" in lower:
            return GeocodingResult(
                query=clean_query,
                latitude=None,
                longitude=None,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message=f"Location query '{clean_query}' could not be resolved to valid coordinates.",
            )

        # 3. Explicit ambiguous simulation or generic ambiguous patterns
        is_ambiguous_query = (
            self.simulate_ambiguous
            or any(lower == p for p in AMBIGUOUS_PATTERNS)
            or (any(p in lower for p in AMBIGUOUS_PATTERNS) and not any(k in lower for k in ["pune", "mumbai", "swargate", "andheri", "dadar"]))
        )

        if is_ambiguous_query:
            candidates = [
                GeocodingCandidate(
                    display_name=f"{clean_query}, Pune, Maharashtra, India",
                    latitude=18.5204,
                    longitude=73.8567,
                    importance=0.6,
                ),
                GeocodingCandidate(
                    display_name=f"{clean_query}, Mumbai, Maharashtra, India",
                    latitude=19.0760,
                    longitude=72.8777,
                    importance=0.58,
                ),
                GeocodingCandidate(
                    display_name=f"{clean_query}, Bengaluru, Karnataka, India",
                    latitude=12.9716,
                    longitude=77.5946,
                    importance=0.55,
                ),
            ]
            return GeocodingResult(
                query=clean_query,
                latitude=candidates[0].latitude,
                longitude=candidates[0].longitude,
                formatted_address=candidates[0].display_name,
                provider=self.provider_name,
                status=GeocodingStatus.AMBIGUOUS,
                confidence=0.45,
                is_verified=False,
                candidates=candidates,
                error_message=f"Query '{clean_query}' is ambiguous across multiple regions; dispatcher verification required.",
            )

        # 4. Known Directory Match
        for key, (lat, lon, addr) in KNOWN_SPATIAL_DIRECTORY.items():
            if key in lower or lower in key:
                return GeocodingResult(
                    query=clean_query,
                    latitude=lat,
                    longitude=lon,
                    formatted_address=addr,
                    provider=self.provider_name,
                    status=GeocodingStatus.SUCCESS,
                    confidence=0.95,
                    is_verified=True,
                    candidates=[
                        GeocodingCandidate(
                            display_name=addr,
                            latitude=lat,
                            longitude=lon,
                            importance=0.88,
                        )
                    ],
                )

        # 5. Default generic resolution fallback (Success with moderate confidence)
        return GeocodingResult(
            query=clean_query,
            latitude=18.5204,
            longitude=73.8567,
            formatted_address=f"{clean_query}, Pune District, Maharashtra, India",
            provider=self.provider_name,
            status=GeocodingStatus.SUCCESS,
            confidence=0.75,
            is_verified=True,
            candidates=[
                GeocodingCandidate(
                    display_name=f"{clean_query}, Pune District, Maharashtra, India",
                    latitude=18.5204,
                    longitude=73.8567,
                    importance=0.7,
                )
            ],
        )

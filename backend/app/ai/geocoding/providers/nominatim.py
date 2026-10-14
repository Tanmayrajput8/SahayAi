"""OpenStreetMap Nominatim REST API Geocoding Provider."""
import logging
import time
from typing import Optional, Dict, Any, List
import httpx

from app.models.location import GeocodingStatus
from app.ai.geocoding.schemas import GeocodingResult, GeocodingCandidate
from app.ai.geocoding.providers.base import GeocodingProvider

logger = logging.getLogger(__name__)


class NominatimGeocodingProvider(GeocodingProvider):
    """
    External Geocoding Provider using OpenStreetMap Nominatim REST API.
    Does NOT download map databases. Communicates directly over HTTPS with
    built-in retries, timeout handling, ambiguity detection, and failure recovery.
    """

    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org/search",
        timeout: float = 5.0,
        max_retries: int = 2,
        user_agent: str = "SahayAI-Emergency-Dispatch/0.1.0 (contact: dispatch@sahayai.internal)",
        timeout_seconds: Optional[float] = None,
    ):
        self.base_url = base_url
        self.timeout = timeout_seconds if timeout_seconds is not None else timeout
        self.max_retries = max_retries
        self.user_agent = user_agent

    @property
    def provider_name(self) -> str:
        return "osm_nominatim"

    def _call_nominatim(self, query: str) -> List[Dict[str, Any]]:
        """Call Nominatim REST API with retries and exponential backoff."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        params = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": 5,
        }

        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(self.base_url, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            return data
                        return []
                    elif resp.status_code in (429, 500, 502, 503, 504):
                        logger.warning("Nominatim HTTP %d on attempt %d/%d", resp.status_code, attempt + 1, self.max_retries + 1)
                        if attempt < self.max_retries:
                            time.sleep(0.5 * (attempt + 1))
                            continue
                    else:
                        logger.warning("Nominatim returned HTTP %d: %s", resp.status_code, resp.text[:200])
                        return []
            except httpx.TimeoutException as exc:
                logger.warning("Nominatim timeout on attempt %d/%d: %s", attempt + 1, self.max_retries + 1, exc)
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))
            except httpx.RequestError as exc:
                logger.warning("Nominatim network error on attempt %d/%d: %s", attempt + 1, self.max_retries + 1, exc)
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))

        if last_exc:
            raise last_exc
        return []

    def geocode(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GeocodingResult:
        """Geocode query string with status classification (success, ambiguous, failed)."""
        clean_query = (query or "").strip()
        if not clean_query:
            return GeocodingResult(
                query=query,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message="Location query is empty.",
            )

        try:
            candidates_raw = self._call_nominatim(clean_query)
        except Exception as exc:
            logger.error("Nominatim geocoding failed for '%s': %s", clean_query, exc)
            return GeocodingResult(
                query=clean_query,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message=f"Geocoding service unavailable or timed out: {exc}",
            )

        if not candidates_raw:
            return GeocodingResult(
                query=clean_query,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message=f"No geographic matches found for location query '{clean_query}'.",
            )

        # Parse candidates
        candidates: List[GeocodingCandidate] = []
        for item in candidates_raw:
            try:
                candidates.append(
                    GeocodingCandidate(
                        display_name=item.get("display_name", ""),
                        latitude=float(item["lat"]),
                        longitude=float(item["lon"]),
                        importance=float(item.get("importance", 0.5)),
                        place_id=str(item.get("place_id", "")),
                        type=item.get("type"),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue

        if not candidates:
            return GeocodingResult(
                query=clean_query,
                provider=self.provider_name,
                status=GeocodingStatus.FAILED,
                confidence=0.0,
                is_verified=False,
                error_message="Invalid coordinate structure in geocoding response.",
            )

        # 1 candidate -> Clear Success
        if len(candidates) == 1:
            top = candidates[0]
            return GeocodingResult(
                query=clean_query,
                latitude=top.latitude,
                longitude=top.longitude,
                formatted_address=top.display_name,
                provider=self.provider_name,
                status=GeocodingStatus.SUCCESS,
                confidence=0.92,
                is_verified=True,
                candidates=candidates,
            )

        # Multiple candidates: check for ambiguity
        top = candidates[0]
        second = candidates[1]
        
        # If top candidate is significantly more important than second, consider success
        if (top.importance - second.importance) >= 0.20:
            return GeocodingResult(
                query=clean_query,
                latitude=top.latitude,
                longitude=top.longitude,
                formatted_address=top.display_name,
                provider=self.provider_name,
                status=GeocodingStatus.SUCCESS,
                confidence=0.82,
                is_verified=True,
                candidates=candidates,
            )

        # Otherwise ambiguous: multiple close matches across distinct points
        return GeocodingResult(
            query=clean_query,
            latitude=top.latitude,
            longitude=top.longitude,
            formatted_address=top.display_name,
            provider=self.provider_name,
            status=GeocodingStatus.AMBIGUOUS,
            confidence=0.50,
            is_verified=False,
            candidates=candidates,
            error_message=(
                f"Ambiguous location query returned {len(candidates)} distinct candidate coordinates. "
                "Dispatcher verification required."
            ),
        )

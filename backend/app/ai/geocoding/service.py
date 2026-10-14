"""Service for geocoding emergency locations and persisting spatial records."""
import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatus
from app.models.location import Location, GeocodingStatus
from app.models.audit import AuditLog, AuditStage
from app.models.human_review import HumanReview, ReviewStatus
from app.ai.geocoding.schemas import GeocodingResult
from app.ai.geocoding.providers.base import GeocodingProvider
from app.ai.geocoding.providers.factory import get_geocoding_provider

logger = logging.getLogger(__name__)


def process_case_geocoding(
    case: Case,
    location_query: Optional[str],
    db: Session,
    provider: Optional[GeocodingProvider] = None,
) -> Tuple[Location, Optional[str]]:
    """
    Geocode an emergency location query, persist spatial records, and audit outcomes.

    Guarantees:
    - If geocoding fails: DO NOT reject the emergency.
    - Mark location unverified (is_verified = False).
    - Allow dispatcher intervention by surfacing in human review.
    - Log the failure immutably in AuditLog.

    Returns:
        Tuple of (Location, review_trigger_reason_or_None)
    """
    if provider is None:
        provider = get_geocoding_provider()

    clean_query = (location_query or "").strip()
    review_trigger: Optional[str] = None

    # 1. Handle Missing / Omitted Location
    if not clean_query:
        loc = case.location
        if not loc:
            loc = Location(case_id=case.id, raw_query="[Location Not Mentioned]")
            db.add(loc)

        loc.raw_query = "[Location Not Mentioned]"
        loc.latitude = None
        loc.longitude = None
        loc.formatted_address = None
        loc.geocoding_provider = provider.provider_name
        loc.status = GeocodingStatus.FAILED
        loc.confidence = 0.0
        loc.is_verified = False
        loc.error_message = "No location extracted from emergency narrative or caller input."

        audit = AuditLog(
            case_id=case.id,
            stage=AuditStage.GEOCODING,
            actor=f"GEOCODER_{provider.provider_name.upper()}",
            action="GEOCODING_FAILED_NO_QUERY",
            details={
                "status": "failed",
                "reason": "Missing location query in caller description",
                "is_verified": False,
            },
        )
        db.add(audit)
        return loc, "Missing emergency location: dispatcher callback or intervention required."

    # 2. Execute Geocoding via Provider
    result: GeocodingResult = provider.geocode(clean_query)

    # 3. Update or Create Location Record
    loc = case.location
    if not loc:
        loc = Location(case_id=case.id, raw_query=clean_query)
        db.add(loc)

    loc.raw_query = clean_query
    loc.formatted_address = result.formatted_address
    loc.latitude = result.latitude
    loc.longitude = result.longitude
    loc.geocoding_provider = result.provider
    loc.status = result.status
    loc.confidence = result.confidence
    loc.is_verified = result.is_verified
    loc.error_message = result.error_message

    # 4. Audit Log
    action_name = f"GEOCODING_{result.status.value.upper()}"
    audit = AuditLog(
        case_id=case.id,
        stage=AuditStage.GEOCODING,
        actor=f"GEOCODER_{provider.provider_name.upper()}",
        action=action_name,
        details={
            "query": clean_query,
            "status": result.status.value,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "formatted_address": result.formatted_address,
            "provider": result.provider,
            "confidence": result.confidence,
            "is_verified": result.is_verified,
            "error_message": result.error_message,
        },
    )
    db.add(audit)

    # 5. Handle Ambiguous & Failed Modes for Dispatcher Intervention
    if result.status == GeocodingStatus.AMBIGUOUS:
        loc.is_verified = False  # Mark unverified
        review_trigger = (
            f"Ambiguous location geocoding for '{clean_query}': multiple candidate sites found. "
            "Dispatcher intervention required to confirm exact landmark."
        )

    elif result.status == GeocodingStatus.FAILED:
        loc.is_verified = False  # Mark unverified
        review_trigger = (
            f"Geocoding failed for location query '{clean_query}': {result.error_message or 'Coordinates unresolved'}. "
            "Dispatcher intervention required to manually set coordinates."
        )

    return loc, review_trigger


def manually_verify_case_location(
    case_id: str,
    latitude: float,
    longitude: float,
    formatted_address: Optional[str],
    dispatcher_id: str,
    db: Session,
) -> Location:
    """
    Allow dispatcher intervention to manually verify or correct emergency coordinates.
    Sets is_verified = True and status = success.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case with ID '{case_id}' not found.")

    loc = case.location
    if not loc:
        loc = Location(case_id=case.id, raw_query=formatted_address or "Manual Dispatcher Entry")
        db.add(loc)

    loc.latitude = latitude
    loc.longitude = longitude
    if formatted_address:
        loc.formatted_address = formatted_address
    loc.geocoding_provider = f"manual_{dispatcher_id}"
    loc.status = GeocodingStatus.SUCCESS
    loc.confidence = 1.0
    loc.is_verified = True
    loc.error_message = None

    audit = AuditLog(
        case_id=case.id,
        stage=AuditStage.GEOCODING,
        actor=f"DISPATCHER_{dispatcher_id}",
        action="LOCATION_MANUALLY_VERIFIED",
        details={
            "latitude": latitude,
            "longitude": longitude,
            "formatted_address": loc.formatted_address,
            "is_verified": True,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(loc)
    return loc

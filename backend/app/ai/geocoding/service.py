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
        # Query for existing location record — never create a second one
        loc = db.query(Location).filter(Location.case_id == case.id).first()
        if loc and loc.latitude is not None and loc.longitude is not None:
            # Preserve caller/device GPS coordinates attached at intake
            case.location = loc
            return loc, None

        if not loc:
            loc = Location(case_id=case.id, raw_query="[Location Not Mentioned]")
            db.add(loc)
        else:
            case.location = loc  # ensure relationship is wired

        loc.raw_query = loc.raw_query or "[Location Not Mentioned]"
        loc.latitude = None
        loc.longitude = None
        loc.formatted_address = None
        loc.geocoding_provider = provider.provider_name
        loc.status = GeocodingStatus.FAILED
        loc.confidence = 0.0
        loc.is_verified = False
        loc.error_message = "No location extracted from emergency narrative or caller input."

        if case.location is None:
            case.location = loc

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

    # 3. Update or Create Location Record — use upsert pattern to prevent duplicate locations.
    # The Location.case_id has a UNIQUE constraint; always query first, update in place.
    loc = db.query(Location).filter(Location.case_id == case.id).first()
    if not loc:
        loc = Location(case_id=case.id, raw_query=clean_query)
        db.add(loc)

    # Wire the relationship without triggering a new INSERT
    if case.location is None or case.location is not loc:
        case.location = loc

    loc.raw_query = clean_query
    if result.latitude is not None and result.longitude is not None:
        loc.formatted_address = result.formatted_address or loc.formatted_address
        loc.latitude = result.latitude
        loc.longitude = result.longitude
        loc.geocoding_provider = result.provider
        loc.status = result.status
        loc.confidence = result.confidence
        loc.is_verified = result.is_verified
        loc.error_message = result.error_message
    else:
        # Preserve caller/device GPS coordinates if already present
        if loc.latitude is None or loc.longitude is None:
            loc.formatted_address = result.formatted_address
            loc.latitude = None
            loc.longitude = None
            loc.geocoding_provider = result.provider
            loc.status = result.status
            loc.confidence = result.confidence
            loc.is_verified = False
            loc.error_message = result.error_message
        else:
            loc.geocoding_provider = loc.geocoding_provider or result.provider

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

    loc = case.location or db.query(Location).filter(Location.case_id == case.id).first()
    if not loc:
        loc = Location(case=case, case_id=case.id, raw_query=formatted_address or "Manual Dispatcher Entry")
        case.location = loc
        db.add(loc)
    else:
        case.location = loc

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

"""Simulated Ambulance and Hospital Resource Verification & Dispatch Service.

Implements resource matching algorithm:
1. Find available ambulances (database verification)
2. Match BLS/ALS requirement (clinical prioritization)
3. Calculate candidate distances (spatial pre-filtering via Haversine)
4. Select top candidates
5. Request route ETA from external routing API (OSRM or OpenRouteService)
   - If routing API fails, uses lightweight Haversine + urban tortuosity fallback
   - Never claims live traffic unless the API actually provides it
6. Select appropriate resource (optimal ambulance + specialized capable hospital with available beds)
7. Store match in database (ResourceMatch entity + AuditLog entry)
8. Update ambulance status (to DISPATCHED) and case status

Handles:
- No resource in system
- Unavailable ambulances (all busy/maintenance)
- No matching ambulance type (ALS vs BLS)
- Invalid or missing emergency location
- External routing API failure (with seamless lightweight fallback)
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType
from app.models.location import Location, GeocodingStatus
from app.models.ambulance import Ambulance, AmbulanceStatus
from app.models.hospital import Hospital
from app.models.resource_match import ResourceMatch
from app.models.audit import AuditLog, AuditStage
from app.models.human_review import HumanReview, ReviewStatus
from app.schemas.resource import AmbulanceResponse, HospitalResponse, ResourceMatchResult
from app.services.routing.base import RoutingProvider
from app.services.routing.factory import get_routing_provider
from app.services.routing.fallback import haversine_distance_km, HaversineFallbackRouter
from app.services.routing.schemas import RouteResult

logger = logging.getLogger(__name__)


# ==============================================================================
# Domain Exceptions
# ==============================================================================

class ResourceVerificationError(Exception):
    """Base exception for resource matching and verification failures."""
    def __init__(self, message: str, code: str = "RESOURCE_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class InvalidLocationError(ResourceVerificationError):
    """Raised when emergency case lacks valid coordinates for routing."""
    def __init__(self, message: str = "Emergency case lacks valid geographic coordinates.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_LOCATION", details=details)


class NoResourceAvailableError(ResourceVerificationError):
    """Raised when no fleet ambulances or hospitals are registered in the system."""
    def __init__(self, message: str = "No emergency resources registered in database.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="NO_RESOURCES", details=details)


class AmbulanceUnavailableError(ResourceVerificationError):
    """Raised when all ambulances are busy, dispatched, or under maintenance."""
    def __init__(self, message: str = "All ambulances are currently busy, dispatched, or in maintenance.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="ALL_AMBULANCES_BUSY", details=details)


class AmbulanceTypeMismatchError(ResourceVerificationError):
    """Raised when no ambulance matching the requested BLS/ALS tier is available."""
    def __init__(self, required_type: AmbulanceType, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        msg = message or f"No available ambulance matching required type '{required_type.value}'."
        super().__init__(msg, code="NO_MATCHING_AMBULANCE_TYPE", details=details)
        self.required_type = required_type


class HospitalUnavailableError(ResourceVerificationError):
    """Raised when no suitable hospital with available beds or required capabilities is found."""
    def __init__(self, message: str = "No capable hospital with available bed capacity.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="NO_HOSPITAL_CAPACITY", details=details)


# ==============================================================================
# Core Verification & Matching Engine
# ==============================================================================

def determine_required_ambulance_type(case: Case) -> AmbulanceType:
    """
    Determine whether ALS or BLS is required based on AI decision or clinical triage priority.
    """
    # Check latest AI decision
    if case.ai_decisions:
        latest_decision = case.ai_decisions[-1]
        if latest_decision.recommended_ambulance_type:
            return latest_decision.recommended_ambulance_type

    # High / Critical severity requires Advanced Life Support (ALS)
    if case.priority in (SeverityLevel.CRITICAL, SeverityLevel.HIGH):
        return AmbulanceType.ALS

    # Check extracted emergency symptoms
    if case.extracted_info:
        ext = case.extracted_info
        em_type = (ext.emergency_type or "").upper()
        symptoms_str = " ".join(ext.symptoms or []).upper()
        if any(keyword in em_type or keyword in symptoms_str for keyword in ("CARDIAC", "HEART", "STROKE", "UNCONSCIOUS", "BREATHING", "BURN", "SEVERE", "TRAUMA")):
            return AmbulanceType.ALS

    return AmbulanceType.BLS


def determine_required_hospital_capabilities(case: Case) -> List[str]:
    """
    Extract required hospital capabilities based on extracted emergency details.
    Returns list of requirements: ["CARDIAC", "TRAUMA", "BURNS", "PEDIATRIC", "ICU"].
    """
    capabilities: List[str] = []
    if case.priority == SeverityLevel.CRITICAL:
        capabilities.append("ICU")

    if case.extracted_info:
        ext = case.extracted_info
        em_type = (ext.emergency_type or "").upper()
        symptoms_str = " ".join(ext.symptoms or []).upper()

        if "CARDIAC" in em_type or "HEART" in symptoms_str or "CHEST PAIN" in symptoms_str:
            capabilities.append("CARDIAC")
        if "TRAUMA" in em_type or "ACCIDENT" in em_type or "FRACTURE" in symptoms_str:
            capabilities.append("TRAUMA")
        if "BURN" in em_type or "FIRE" in symptoms_str:
            capabilities.append("BURNS")
        if "PEDIATRIC" in em_type or "CHILD" in em_type or "INFANT" in symptoms_str:
            capabilities.append("PEDIATRIC")

    return capabilities


def verify_and_match_resources(
    case_id: str,
    db: Session,
    routing_provider: Optional[RoutingProvider] = None,
    top_candidates_count: int = 3,
    strict_ambulance_type: bool = False,
    auto_dispatch: bool = True,
) -> Tuple[ResourceMatch, ResourceMatchResult]:
    """
    Executes the full simulated ambulance and hospital resource verification algorithm.

    Algorithm:
    1. Verify emergency location coordinates.
    2. Query available ambulances and check capacity.
    3. Match BLS/ALS capability.
    4. Calculate spatial candidate distances (Haversine pre-filter).
    5. Select top N candidates.
    6. Request driving route ETA from external routing API (OSRM/ORS) with mathematical fallback.
    7. Select optimal ambulance and capable hospital with available bed capacity.
    8. Store match record and immutable audit trail.
    9. Update ambulance status to DISPATCHED.

    Guarantees:
    - Never crashes on routing API failures; uses documented fallback.
    - Never claims live traffic information unless the API actually provides it.
    - Audits every verification step for full transparency.
    """
    if routing_provider is None:
        routing_provider = get_routing_provider()

    case: Optional[Case] = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case with ID '{case_id}' does not exist.")

    # -------------------------------------------------------------------------
    # STEP 1: Verify Emergency Location Coordinates
    # -------------------------------------------------------------------------
    loc: Optional[Location] = case.location
    if not loc or loc.latitude is None or loc.longitude is None or loc.status == GeocodingStatus.FAILED:
        logger.warning("Resource matching halted: Case '%s' has invalid or missing coordinates.", case.id)
        # Record audit log
        audit_fail = AuditLog(
            case_id=case.id,
            stage=AuditStage.RESOURCE_MATCHING,
            actor="RESOURCE_VERIFIER",
            action="RESOURCE_MATCH_FAILED_INVALID_LOCATION",
            details={
                "reason": "Invalid or missing geocoded coordinates",
                "location_status": loc.status.value if loc else "NO_LOCATION",
                "raw_query": loc.raw_query if loc else None,
            },
        )
        db.add(audit_fail)

        # Escalate to human review
        if case.status != CaseStatus.UNDER_REVIEW:
            case.status = CaseStatus.UNDER_REVIEW
            review = HumanReview(
                case_id=case.id,
                review_status=ReviewStatus.PENDING,
                trigger_reason="Resource matching blocked: Emergency location coordinates missing or unverified.",
                original_decision={"status": "BLOCKED_LOCATION"},
            )
            db.add(review)

        db.commit()
        raise InvalidLocationError(
            f"Case '{case.id}' has unresolvable coordinates. Dispatcher location verification required.",
            details={"location_status": loc.status.value if loc else "MISSING"},
        )

    emergency_lat = float(loc.latitude)
    emergency_lon = float(loc.longitude)

    # -------------------------------------------------------------------------
    # STEP 2 & 3: Find Available Ambulance & Match BLS/ALS
    # -------------------------------------------------------------------------
    total_ambulances = db.query(Ambulance).count()
    if total_ambulances == 0:
        _log_audit_failure(db, case.id, "NO_AMBULANCES_IN_DATABASE", "Fleet table is empty.")
        raise NoResourceAvailableError("No ambulances registered in database.")

    available_ambulances: List[Ambulance] = (
        db.query(Ambulance)
        .filter(Ambulance.status == AmbulanceStatus.AVAILABLE)
        .all()
    )

    if not available_ambulances:
        _log_audit_failure(db, case.id, "ALL_AMBULANCES_UNAVAILABLE", "All ambulances are busy or in maintenance.")
        raise AmbulanceUnavailableError("All fleet ambulances are currently busy, dispatched, or in maintenance.")

    required_type = determine_required_ambulance_type(case)
    matching_type_ambulances = [a for a in available_ambulances if a.ambulance_type == required_type]

    type_fallback_used = False
    type_fallback_note = ""

    if not matching_type_ambulances:
        if strict_ambulance_type:
            _log_audit_failure(
                db,
                case.id,
                "NO_MATCHING_AMBULANCE_TYPE",
                f"Required {required_type.value}, but none available among {len(available_ambulances)} active units.",
            )
            raise AmbulanceTypeMismatchError(
                required_type,
                message=f"No available ambulance matching required type '{required_type.value}'.",
                details={
                    "required_type": required_type.value,
                    "available_types": [a.ambulance_type.value for a in available_ambulances],
                },
            )
        else:
            # Resilient fallback: Use closest available ambulance of the alternative type
            type_fallback_used = True
            matching_type_ambulances = available_ambulances
            alt_type = matching_type_ambulances[0].ambulance_type.value
            type_fallback_note = (
                f"Required {required_type.value} ambulance was unavailable. "
                f"Dispatched available {alt_type} ambulance with emergency paramedic protocol."
            )
            logger.warning("Ambulance type mismatch for case '%s': %s", case.id, type_fallback_note)

    # -------------------------------------------------------------------------
    # STEP 4: Calculate Candidate Distances & Select Top Candidates
    # -------------------------------------------------------------------------
    candidates_with_dist: List[Tuple[Ambulance, float]] = []
    for amb in matching_type_ambulances:
        straight_km = haversine_distance_km(amb.latitude, amb.longitude, emergency_lat, emergency_lon)
        candidates_with_dist.append((amb, straight_km))

    # Sort candidates by straight-line distance
    candidates_with_dist.sort(key=lambda x: x[1])
    top_candidates = candidates_with_dist[:top_candidates_count]

    # -------------------------------------------------------------------------
    # STEP 5: Request Route ETA from Routing API (with Fallback)
    # -------------------------------------------------------------------------
    evaluated_candidates: List[Dict[str, Any]] = []
    best_ambulance: Optional[Ambulance] = None
    best_amb_route: Optional[RouteResult] = None
    min_eta = float("inf")

    for amb, straight_km in top_candidates:
        route_res: RouteResult = routing_provider.calculate_route(
            origin_lat=amb.latitude,
            origin_lon=amb.longitude,
            dest_lat=emergency_lat,
            dest_lon=emergency_lon,
        )

        candidate_info = {
            "ambulance_id": amb.id,
            "vehicle_number": amb.vehicle_number,
            "ambulance_type": amb.ambulance_type.value,
            "base_station": amb.base_station,
            "haversine_distance_km": round(straight_km, 2),
            "route_distance_km": route_res.distance_km,
            "route_eta_minutes": route_res.duration_minutes,
            "is_routing_fallback": route_res.is_fallback,
            "routing_provider": route_res.provider,
            "has_live_traffic": route_res.has_live_traffic,
        }
        evaluated_candidates.append(candidate_info)

        # Select ambulance with minimum estimated time of arrival (ETA)
        if route_res.duration_minutes < min_eta:
            min_eta = route_res.duration_minutes
            best_ambulance = amb
            best_amb_route = route_res

    if not best_ambulance or not best_amb_route:
        raise ResourceVerificationError("Failed to evaluate candidate routes for available fleet.")

    # -------------------------------------------------------------------------
    # STEP 6: Select Appropriate Hospital (Beds & Capabilities)
    # -------------------------------------------------------------------------
    total_hospitals = db.query(Hospital).count()
    if total_hospitals == 0:
        _log_audit_failure(db, case.id, "NO_HOSPITALS_IN_DATABASE", "Hospitals table is empty.")
        raise NoResourceAvailableError("No hospitals registered in database.")

    active_hospitals: List[Hospital] = (
        db.query(Hospital)
        .filter(Hospital.is_active == True)
        .all()
    )

    if not active_hospitals:
        _log_audit_failure(db, case.id, "NO_ACTIVE_HOSPITALS", "All hospitals are marked inactive.")
        raise HospitalUnavailableError("All registered hospitals are currently inactive.")

    # Bed availability verification
    hospitals_with_beds = [h for h in active_hospitals if (h.available_beds or 0) > 0]
    if not hospitals_with_beds:
        _log_audit_failure(db, case.id, "HOSPITAL_BED_CAPACITY_EXHAUSTED", "No active hospital has available beds.")
        raise HospitalUnavailableError("All active hospitals report 0 available general beds.")

    required_caps = determine_required_hospital_capabilities(case)

    # Filter hospitals meeting required capabilities and ICU beds if needed
    capable_hospitals: List[Hospital] = []
    for h in hospitals_with_beds:
        meets_caps = True
        if "CARDIAC" in required_caps and not h.has_cardiac_care:
            meets_caps = False
        if "TRAUMA" in required_caps and not h.has_trauma_center:
            meets_caps = False
        if "BURNS" in required_caps and not h.has_burn_unit:
            meets_caps = False
        if "PEDIATRIC" in required_caps and not h.has_pediatric_icu:
            meets_caps = False
        if "ICU" in required_caps and (h.available_icu_beds or 0) <= 0:
            meets_caps = False

        if meets_caps:
            capable_hospitals.append(h)

    # If no hospital meets ALL strict capabilities, fallback to all hospitals with available beds
    hospital_capability_fallback = False
    if not capable_hospitals:
        hospital_capability_fallback = True
        capable_hospitals = hospitals_with_beds
        logger.warning(
            "No hospital met all strict capabilities (%s) with available beds. Falling back to nearest active hospital with general beds.",
            required_caps,
        )

    # Route candidate hospitals from emergency location
    best_hospital: Optional[Hospital] = None
    best_hosp_route: Optional[RouteResult] = None
    min_hosp_eta = float("inf")

    # Sort capable hospitals by straight-line distance and evaluate top candidates
    hosp_candidates = sorted(
        capable_hospitals,
        key=lambda h: haversine_distance_km(emergency_lat, emergency_lon, h.latitude, h.longitude),
    )[:top_candidates_count]

    for hosp in hosp_candidates:
        h_route = routing_provider.calculate_route(
            origin_lat=emergency_lat,
            origin_lon=emergency_lon,
            dest_lat=hosp.latitude,
            dest_lon=hosp.longitude,
        )
        if h_route.duration_minutes < min_hosp_eta:
            min_hosp_eta = h_route.duration_minutes
            best_hospital = hosp
            best_hosp_route = h_route

    if not best_hospital or not best_hosp_route:
        raise HospitalUnavailableError("Failed to compute route to capable hospital facility.")

    # -------------------------------------------------------------------------
    # STEP 7: Store Match in Database
    # -------------------------------------------------------------------------
    # Calculate match score (0.0 to 1.0)
    # Higher score = lower ambulance ETA, lower hospital ETA, specialized match
    eta_penalty = min(0.40, (best_amb_route.duration_minutes / 60.0) * 0.40)
    spec_bonus = 0.20 if not hospital_capability_fallback else 0.05
    type_bonus = 0.20 if not type_fallback_used else 0.05
    base_score = 0.60
    match_score = max(0.20, min(1.0, round(base_score + spec_bonus + type_bonus - eta_penalty, 2)))

    # Synthesize explainable selection rationale
    reasons: List[str] = [
        f"Matched {best_ambulance.ambulance_type.value} ambulance '{best_ambulance.vehicle_number}' "
        f"from {best_ambulance.base_station} ({best_amb_route.distance_km} km, ETA: {best_amb_route.duration_minutes} mins).",
        f"Destination: {best_hospital.name} ({best_hosp_route.distance_km} km, {best_hospital.available_beds} beds free, "
        f"{best_hospital.available_icu_beds} ICU beds free).",
    ]
    if type_fallback_used:
        reasons.append(f"[NOTE] {type_fallback_note}")
    if hospital_capability_fallback:
        reasons.append(f"[WARNING] Secondary facility chosen: specialized bed constraints required fallback to {best_hospital.name}.")
    if best_amb_route.is_fallback or best_hosp_route.is_fallback:
        reasons.append(f"[ROUTING] {best_amb_route.traffic_disclaimer}")
    else:
        reasons.append(f"[ROUTING] Route calculated via {best_amb_route.provider}. {best_amb_route.traffic_disclaimer}")

    selection_reason = " ".join(reasons)

    resource_match = ResourceMatch(
        case_id=case.id,
        ambulance_id=best_ambulance.id,
        hospital_id=best_hospital.id,
        ambulance_distance_km=best_amb_route.distance_km,
        ambulance_eta_minutes=best_amb_route.duration_minutes,
        hospital_distance_km=best_hosp_route.distance_km,
        match_score=match_score,
        selection_reason=selection_reason,
        is_dispatched=auto_dispatch,
        dispatched_at=datetime.now(timezone.utc) if auto_dispatch else None,
    )
    db.add(resource_match)

    # -------------------------------------------------------------------------
    # STEP 8: Update Ambulance Status & Case Status
    # -------------------------------------------------------------------------
    if auto_dispatch:
        best_ambulance.status = AmbulanceStatus.DISPATCHED
        if case.status in (CaseStatus.PENDING, CaseStatus.TRIAGED):
            case.status = CaseStatus.DISPATCHED

    # Audit Trail (Immutable)
    audit = AuditLog(
        case_id=case.id,
        stage=AuditStage.RESOURCE_MATCHING,
        actor="RESOURCE_ALLOCATION_ENGINE",
        action="RESOURCE_MATCHED_AND_DISPATCHED" if auto_dispatch else "RESOURCE_MATCH_PREVIEWED",
        details={
            "matched_ambulance": {
                "id": best_ambulance.id,
                "vehicle_number": best_ambulance.vehicle_number,
                "type": best_ambulance.ambulance_type.value,
                "distance_km": best_amb_route.distance_km,
                "eta_minutes": best_amb_route.duration_minutes,
            },
            "matched_hospital": {
                "id": best_hospital.id,
                "name": best_hospital.name,
                "distance_km": best_hosp_route.distance_km,
                "available_beds": best_hospital.available_beds,
                "available_icu_beds": best_hospital.available_icu_beds,
            },
            "routing_telemetry": {
                "ambulance_route_provider": best_amb_route.provider,
                "is_fallback": best_amb_route.is_fallback or best_hosp_route.is_fallback,
                "has_live_traffic": best_amb_route.has_live_traffic,
                "traffic_disclaimer": best_amb_route.traffic_disclaimer,
            },
            "candidates_evaluated_count": len(evaluated_candidates),
            "match_score": match_score,
            "type_fallback_used": type_fallback_used,
            "hospital_capability_fallback": hospital_capability_fallback,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(resource_match)
    db.refresh(best_ambulance)
    db.refresh(best_hospital)
    db.refresh(case)

    # Format result response
    result_response = ResourceMatchResult(
        matched_ambulance=AmbulanceResponse.model_validate(best_ambulance),
        ambulance_distance_km=best_amb_route.distance_km,
        ambulance_eta_minutes=best_amb_route.duration_minutes,
        matched_hospital=HospitalResponse.model_validate(best_hospital),
        hospital_distance_km=best_hosp_route.distance_km,
        explanation=selection_reason,
        match_score=match_score,
        is_dispatched=auto_dispatch,
        routing_provider=best_amb_route.provider,
        has_live_traffic=best_amb_route.has_live_traffic,
        is_routing_fallback=best_amb_route.is_fallback or best_hosp_route.is_fallback,
        traffic_disclaimer=best_amb_route.traffic_disclaimer,
    )

    return resource_match, result_response


def _log_audit_failure(db: Session, case_id: str, action: str, reason: str):
    """Helper to record audit failure entries."""
    audit = AuditLog(
        case_id=case_id,
        stage=AuditStage.RESOURCE_MATCHING,
        actor="RESOURCE_ALLOCATION_ENGINE",
        action=f"RESOURCE_MATCH_FAILED_{action}",
        details={"error_reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    db.add(audit)
    db.commit()

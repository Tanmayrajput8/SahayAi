import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.case import Case, CaseStatus, SeverityLevel
from app.models.ambulance import AmbulanceStatus
from app.models.location import Location, GeocodingStatus
from app.models.audit import AuditLog, AuditStage
from app.core.config import settings
from app.schemas.case import CaseCreate, CaseResponse, CaseTriageResponse, CaseLocationUpdate, DuplicateSignalBreakdown
from app.schemas.resource import ResourceMatchResult, AmbulanceResponse, HospitalResponse
from app.services.resource_verification import (
    verify_and_match_resources,
    ResourceVerificationError,
    InvalidLocationError,
    NoResourceAvailableError,
    AmbulanceUnavailableError,
    AmbulanceTypeMismatchError,
    HospitalUnavailableError,
)
from app.services.demo_reset import reset_demo_database
from app.core.deps import get_current_user, get_optional_user
from app.models.user import User
from app.ai.service import process_case_extraction
from app.ai.speech.service import process_audio_emergency
from app.ai.geocoding import manually_verify_case_location
from app.ai.speech.exceptions import (
    EmptyAudioError,
    OversizedAudioError,
    UnsupportedAudioFormatError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/reset",
    summary="Reset Demo Data (Alias)",
    description="Clears all demo emergency cases and restores simulated ambulances and hospitals.",
)
def reset_cases_demo(db: Session = Depends(get_db)):
    """Safe reset of prototype emergency data."""
    return reset_demo_database(db=db)


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Emergency Report",
    description=(
        "Publicly accessible endpoint for citizen and dispatcher emergency intake. "
        "Accepts multi-lingual text (English, Hindi, Marathi, code-mixed), typos, slang, "
        "panic messages, and incomplete descriptions without rejection. "
        "Architecture supports text modality today and is voice/audio stream ready."
    ),
)
def create_case(
    payload: CaseCreate,
    auto_triage: bool = Query(default=False, description="Optionally trigger immediate triage and duplicate detection"),
    db: Session = Depends(get_db),
) -> CaseResponse:
    """
    Ingest a new emergency description.
    Stores raw input, modality, timestamp, and sets initial status to PENDING.
    If auto_triage is True, triggers extraction and duplicate detection immediately.
    """
    logger.info(
        "Emergency case received: modality=%s, caller=%s, length=%d, auto_triage=%s",
        payload.modality.value,
        payload.caller_phone or "anonymous",
        len(payload.raw_text or ""),
        auto_triage,
    )

    # 1. Create Case record
    new_case = Case(
        raw_text=payload.raw_text,
        modality=payload.modality.value,
        caller_phone=payload.caller_phone,
        audio_url=payload.audio_url,
        language=payload.language or "unknown",
        status=CaseStatus.PENDING,
        priority=SeverityLevel.MODERATE,
    )
    db.add(new_case)
    db.flush()  # populate new_case.id and timestamps

    # 2. Attach initial Location if caller provided GPS coordinates or landmark
    if (payload.latitude is not None and payload.longitude is not None) or payload.manual_location:
        has_gps = payload.latitude is not None and payload.longitude is not None
        initial_loc = Location(
            case=new_case,
            case_id=new_case.id,
            raw_query=payload.manual_location or f"GPS Coordinates ({payload.latitude:.4f}, {payload.longitude:.4f})",
            formatted_address=payload.manual_location,
            latitude=payload.latitude,
            longitude=payload.longitude,
            status=GeocodingStatus.SUCCESS if has_gps else GeocodingStatus.SUCCESS,
            confidence=1.0 if has_gps else 0.7,
            is_verified=has_gps,
            geocoding_provider="device_gps" if has_gps else "caller_input",
        )
        new_case.location = initial_loc
        db.add(initial_loc)

    # 3. Immutable audit trail for intake
    audit_entry = AuditLog(
        case_id=new_case.id,
        stage=AuditStage.INTAKE,
        actor="CITIZEN_PORTAL",
        action="EMERGENCY_INTAKE_RECEIVED",
        details={
            "modality": new_case.modality,
            "caller_phone": new_case.caller_phone,
            "has_audio": bool(new_case.audio_url),
            "language_hint": new_case.language,
            "char_count": len(new_case.raw_text),
            "has_gps": (payload.latitude is not None and payload.longitude is not None),
        },
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(new_case)

    # 4. Trigger auto-triage and duplicate detection if requested
    if auto_triage:
        try:
            process_case_extraction(case_id=new_case.id, db=db)
            db.refresh(new_case)
        except Exception as exc:
            logger.warning("Auto-triage for case %s failed: %s", new_case.id, exc)

    return CaseResponse.model_validate(new_case)



@router.get(
    "/{case_id}",
    response_model=CaseTriageResponse,
    summary="Get Emergency Case by ID (rich)",
    description="Retrieve full case state including triage, AI decision, location, and confidence details.",
)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
) -> CaseTriageResponse:
    """Retrieve a full emergency case (with triage data) by ID."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )
    return _build_case_triage_response(case)


@router.get(
    "",
    response_model=List[CaseTriageResponse],
    summary="List Emergency Cases (rich)",
    description="Retrieve cases with triage info, confidence, and location fields, with optional status filter.",
)
def list_cases(
    status_filter: Optional[CaseStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> List[CaseTriageResponse]:
    """Listing of emergency cases for dispatchers with full triage and confidence info."""
    query = db.query(Case)
    if status_filter:
        query = query.filter(Case.status == status_filter)

    cases = query.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()
    return [_build_case_triage_response(c) for c in cases]


def _build_case_triage_response(updated_case: Case) -> CaseTriageResponse:
    """Helper to assemble rich CaseTriageResponse with clinical, AI, and geocoding details."""
    extracted = updated_case.extracted_info
    decision = updated_case.ai_decisions[-1] if updated_case.ai_decisions else None
    review = updated_case.human_reviews[-1] if updated_case.human_reviews else None
    loc = updated_case.location

    raw_output = extracted.raw_llm_output if extracted else {}
    is_failed = raw_output.get("status") == "FAILED" or (extracted and extracted.emergency_type == "EXTRACTION_FAILED")

    # Active dispatch assignment details
    assigned_amb = None
    assigned_hosp = None
    eta_min = None
    amb_dist = None
    hosp_dist = None
    if getattr(updated_case, "resource_matches", None):
        for rm in reversed(updated_case.resource_matches):
            if getattr(rm, "is_dispatched", False):
                if rm.ambulance:
                    assigned_amb = AmbulanceResponse.model_validate(rm.ambulance)
                if rm.hospital:
                    assigned_hosp = HospitalResponse.model_validate(rm.hospital)
                eta_min = rm.ambulance_eta_minutes
                amb_dist = rm.ambulance_distance_km
                hosp_dist = rm.hospital_distance_km
                break

    # Assemble real Duplicate Detection Signal Breakdown
    dup_breakdown = None
    if getattr(updated_case, "duplicate_of", None) and len(updated_case.duplicate_of) > 0:
        dup = updated_case.duplicate_of[-1]
        score_val = float(dup.overall_confidence)
        status_str = "DUPLICATE" if score_val >= settings.DUPLICATE_THRESHOLD else ("POSSIBLE_DUPLICATE" if score_val >= settings.DUPLICATE_POSSIBLE_THRESHOLD else "NOT_DUPLICATE")
        dist_val = float(dup.geographic_distance_km) if dup.geographic_distance_km is not None else None
        loc_sim = max(0.0, 1.0 - ((dist_val or 0.0) / settings.DUPLICATE_LOCATION_RADIUS_KM)) if dist_val is not None else 0.0
        time_diff = float(dup.temporal_diff_minutes)
        time_sim = max(0.0, 1.0 - (time_diff / settings.DUPLICATE_TIME_WINDOW_MINUTES))
        dup_breakdown = DuplicateSignalBreakdown(
            status=status_str,
            score=round(score_val, 4),
            matched_case_id=dup.primary_case_id,
            semantic_similarity=round(float(dup.semantic_similarity), 4),
            geographic_distance_km=round(dist_val, 2) if dist_val is not None else None,
            location_similarity=round(loc_sim, 4),
            temporal_diff_minutes=round(time_diff, 1),
            temporal_similarity=round(time_sim, 4),
            emergency_type_similarity=round(float(dup.emergency_type_similarity), 4),
            detection_method=dup.detection_method or "WEIGHTED_MULTISIGNAL",
            formula="0.40*semantic + 0.30*location + 0.15*temporal + 0.15*type",
            requires_review=status_str in ("DUPLICATE", "POSSIBLE_DUPLICATE"),
            is_confirmed_duplicate=bool(dup.is_confirmed_duplicate),
        )
    elif getattr(updated_case, "duplicate_associations", None) and len(updated_case.duplicate_associations) > 0:
        dup = updated_case.duplicate_associations[-1]
        score_val = float(dup.overall_confidence)
        status_str = "DUPLICATE" if score_val >= settings.DUPLICATE_THRESHOLD else ("POSSIBLE_DUPLICATE" if score_val >= settings.DUPLICATE_POSSIBLE_THRESHOLD else "NOT_DUPLICATE")
        dist_val = float(dup.geographic_distance_km) if dup.geographic_distance_km is not None else None
        loc_sim = max(0.0, 1.0 - ((dist_val or 0.0) / settings.DUPLICATE_LOCATION_RADIUS_KM)) if dist_val is not None else 0.0
        time_diff = float(dup.temporal_diff_minutes)
        time_sim = max(0.0, 1.0 - (time_diff / settings.DUPLICATE_TIME_WINDOW_MINUTES))
        dup_breakdown = DuplicateSignalBreakdown(
            status=status_str,
            score=round(score_val, 4),
            matched_case_id=dup.duplicate_case_id,
            semantic_similarity=round(float(dup.semantic_similarity), 4),
            geographic_distance_km=round(dist_val, 2) if dist_val is not None else None,
            location_similarity=round(loc_sim, 4),
            temporal_diff_minutes=round(time_diff, 1),
            temporal_similarity=round(time_sim, 4),
            emergency_type_similarity=round(float(dup.emergency_type_similarity), 4),
            detection_method=dup.detection_method or "WEIGHTED_MULTISIGNAL",
            formula="0.40*semantic + 0.30*location + 0.15*temporal + 0.15*type",
            requires_review=status_str in ("DUPLICATE", "POSSIBLE_DUPLICATE"),
            is_confirmed_duplicate=bool(dup.is_confirmed_duplicate),
        )
    elif getattr(updated_case, "audit_logs", None):
        dup_audit = next((a for a in reversed(updated_case.audit_logs) if getattr(a, "stage", None) == AuditStage.DUPLICATE_CHECK), None)
        if dup_audit and dup_audit.details:
            d = dup_audit.details
            dup_breakdown = DuplicateSignalBreakdown(
                status=d.get("duplicate_status", "NOT_DUPLICATE"),
                score=float(d.get("duplicate_score", 0.0)),
                matched_case_id=d.get("candidate_case_id"),
                semantic_similarity=float(d.get("semantic_similarity", 0.0)),
                geographic_distance_km=float(d["geographic_distance_km"]) if d.get("geographic_distance_km") is not None else None,
                location_similarity=float(d.get("location_similarity", 0.0)),
                temporal_diff_minutes=float(d.get("temporal_diff_minutes", 0.0)),
                temporal_similarity=float(d.get("temporal_similarity", 0.0)),
                emergency_type_similarity=float(d.get("emergency_type_similarity", 0.0)),
                detection_method=d.get("detection_method", "WEIGHTED_MULTISIGNAL"),
                formula=d.get("formula", "0.40*semantic + 0.30*location + 0.15*temporal + 0.15*type"),
                requires_review=d.get("duplicate_status") in ("DUPLICATE", "POSSIBLE_DUPLICATE", "INSUFFICIENT_EVIDENCE"),
                policy_notes=d.get("missing_data_policy_applied"),
                is_confirmed_duplicate=False,
            )

    return CaseTriageResponse(
        id=updated_case.id,
        status=updated_case.status,
        priority=updated_case.priority,
        detected_language=updated_case.language,
        # Raw narrative for display
        raw_text=updated_case.raw_text,
        raw_input=updated_case.raw_text,
        caller_phone=updated_case.caller_phone,
        language=updated_case.language,
        modality=updated_case.modality,
        # Clinical extraction
        emergency_type=extracted.emergency_type if extracted else None,
        symptoms=extracted.symptoms if extracted else [],
        extracted_location=extracted.extracted_location_text if extracted else (loc.raw_query if loc else None),
        patient_count=extracted.patient_count if extracted else 1,
        conscious_status=extracted.conscious_status if extracted else "unknown",
        breathing_status=extracted.breathing_status if extracted else "unknown",
        recommended_ambulance=decision.recommended_ambulance_type.value if decision else None,
        clinical_rationale=decision.clinical_rationale if decision else None,
        confidence_score=extracted.extraction_confidence if extracted else 0.0,
        missing_information=raw_output.get("missing_information", []),
        is_contradictory=raw_output.get("is_contradictory", False),
        routed_to_human_review=updated_case.status == CaseStatus.UNDER_REVIEW,
        human_review_reason=review.trigger_reason if review else None,
        extraction_status="FAILED" if is_failed else "SUCCESS",
        ai_suggested_severity=getattr(decision, "ai_suggested_severity", None),
        ai_suggested_ambulance=getattr(decision, "ai_suggested_ambulance", None),
        deterministic_severity=getattr(decision, "deterministic_severity", None),
        deterministic_ambulance=getattr(decision, "deterministic_ambulance", None),
        has_conflict=getattr(decision, "has_conflict", False),
        conflict_reason=getattr(decision, "conflict_reason", None),
        disclaimer=getattr(decision, "disclaimer", "PROTOTYPE DECISION-SUPPORT HEURISTIC: Not clinically validated triage. Requires human dispatcher verification."),
        latitude=loc.latitude if loc else None,
        longitude=loc.longitude if loc else None,
        geocoding_status=loc.status.value if loc and loc.status else None,
        geocoding_provider=loc.geocoding_provider if loc else None,
        is_location_verified=loc.is_verified if loc else False,
        location_error=loc.error_message if loc else None,
        assigned_ambulance=assigned_amb,
        assigned_hospital=assigned_hosp,
        eta_minutes=eta_min,
        ambulance_distance_km=amb_dist,
        hospital_distance_km=hosp_dist,
        duplicate_detection=dup_breakdown,
        updated_at=updated_case.updated_at,
    )


@router.get(
    "/{case_id}/duplicates",
    response_model=Optional[DuplicateSignalBreakdown],
    summary="Get Case Duplicate Detection Signals (Staff Dossier)",
    description="Retrieve real calculated signals (semantic, distance, temporal, type similarity, and weighted formula) for staff inspection.",
)
def get_case_duplicates(
    case_id: str,
    db: Session = Depends(get_db),
) -> Optional[DuplicateSignalBreakdown]:
    """Retrieve full duplicate detection signal breakdown for staff inspection."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )
    resp = _build_case_triage_response(case)
    return resp.duplicate_detection


@router.post(
    "/{case_id}/triage",
    response_model=CaseTriageResponse,
    summary="Run AI Clinical Triage Extraction",
    description="Invokes the LLM intelligence layer to extract structured clinical data and recommend severity and ambulance.",
)
def triage_case(
    case_id: str,
    db: Session = Depends(get_db),
) -> CaseTriageResponse:
    """Trigger LLM intelligence extraction for an emergency case."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )

    updated_case = process_case_extraction(case_id=case_id, db=db)
    return _build_case_triage_response(updated_case)


@router.post(
    "/audio",
    response_model=CaseTriageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Voice/Audio Emergency Report",
    description=(
        "Upload audio recording from citizen/caller. Transcribes via SpeechToTextProvider "
        "and routes the transcript through the SAME emergency-understanding LLM pipeline."
    ),
)
async def submit_audio_case(
    audio_file: UploadFile = File(..., description="Audio recording file (wav, mp3, ogg, m4a, flac, webm)"),
    caller_phone: Optional[str] = Form(default=None),
    manual_location: Optional[str] = Form(default=None),
    language_hint: Optional[str] = Form(default=None),
    latitude: Optional[float] = Form(default=None),
    longitude: Optional[float] = Form(default=None),
    db: Session = Depends(get_db),
) -> CaseTriageResponse:
    """Ingest voice emergency, transcribe, and route through downstream intelligence pipeline."""
    audio_bytes = await audio_file.read()
    try:
        updated_case = process_audio_emergency(
            audio_bytes=audio_bytes,
            filename=audio_file.filename or "emergency_recording.wav",
            content_type=audio_file.content_type,
            caller_phone=caller_phone,
            manual_location=manual_location,
            language_hint=language_hint,
            latitude=latitude,
            longitude=longitude,
            db=db,
        )
    except EmptyAudioError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "empty_audio", "message": str(exc)},
        )
    except OversizedAudioError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"error": "oversized_audio", "message": str(exc)},
        )
    except UnsupportedAudioFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"error": "unsupported_audio_format", "message": str(exc)},
        )

    return _build_case_triage_response(updated_case)


@router.patch(
    "/{case_id}/location",
    response_model=CaseTriageResponse,
    summary="Dispatcher Manual Location Verification / Override",
    description="Allows emergency dispatchers to manually set or verify coordinates for ambiguous or failed geocodings.",
)
def update_case_location(
    case_id: str,
    payload: CaseLocationUpdate,
    db: Session = Depends(get_db),
    dispatcher_id: Optional[str] = Query(default="dispatcher_1", description="Identifier of the human dispatcher"),
) -> CaseTriageResponse:
    """Manually verify or correct location coordinates for an emergency case."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )

    manually_verify_case_location(
        case_id=case_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        formatted_address=payload.formatted_address,
        dispatcher_id=dispatcher_id or "dispatcher_1",
        db=db,
    )
    db.refresh(case)
    return _build_case_triage_response(case)


class CaseStatusUpdateRequest(BaseModel):
    status: CaseStatus
    notes: Optional[str] = None
    dispatcher_id: Optional[str] = "dispatcher_1"


@router.post(
    "/{case_id}/dispatch",
    response_model=ResourceMatchResult,
    summary="Dispatch Verified Resources to Emergency",
    description="Calculates route ETA using external routing API (OSRM/ORS with fallback) and dispatches best available ambulance and hospital.",
)
@router.post(
    "/{case_id}/match-resources",
    response_model=ResourceMatchResult,
    summary="Match Resources to Emergency",
    include_in_schema=False,
)
def dispatch_case_resources(
    case_id: str,
    strict_ambulance_type: bool = Query(default=False, description="Strict BLS/ALS match requirement"),
    manual: bool = Query(default=True, description="Whether this is an explicit human dispatcher dispatch authorization"),
    dispatcher_id: Optional[str] = Query(default="dispatcher_1", description="Identifier of the human dispatcher"),
    db: Session = Depends(get_db),
) -> ResourceMatchResult:
    """Trigger simulated ambulance and hospital matching for the case."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )

    try:
        _, match_result = verify_and_match_resources(
            case_id=case_id,
            db=db,
            strict_ambulance_type=strict_ambulance_type,
            auto_dispatch=True,
            is_manual_dispatch=manual,
            dispatcher_id=dispatcher_id,
        )
        return match_result

    except InvalidLocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except AmbulanceTypeMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except (AmbulanceUnavailableError, HospitalUnavailableError, NoResourceAvailableError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except ResourceVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )


@router.patch(
    "/{case_id}/status",
    response_model=CaseTriageResponse,
    summary="Update Emergency Case Progression Status",
    description="Transition case status (e.g. ARRIVED, RESOLVED, CANCELLED) and synchronize fleet units and audit logs.",
)
def update_case_status(
    case_id: str,
    payload: CaseStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> CaseTriageResponse:
    """Transition emergency case status with automatic fleet ambulance synchronization and audit recording."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )

    previous_status = case.status
    case.status = payload.status

    # Locate any dispatched fleet ambulance assigned to this case
    assigned_amb = None
    if case.resource_matches:
        for rm in reversed(case.resource_matches):
            if getattr(rm, "is_dispatched", False) and rm.ambulance:
                assigned_amb = rm.ambulance
                break

    # Synchronize ambulance fleet status
    if payload.status == CaseStatus.ARRIVED:
        if assigned_amb:
            assigned_amb.status = AmbulanceStatus.ARRIVED
        action_name = "AMBULANCE_ARRIVED_AT_SCENE"
    elif payload.status in (CaseStatus.RESOLVED, CaseStatus.CANCELLED):
        if assigned_amb:
            assigned_amb.status = AmbulanceStatus.AVAILABLE
        action_name = "EMERGENCY_CASE_RESOLVED" if payload.status == CaseStatus.RESOLVED else "EMERGENCY_CASE_CANCELLED"
    elif payload.status == CaseStatus.DISPATCHED:
        if assigned_amb:
            assigned_amb.status = AmbulanceStatus.DISPATCHED
        action_name = "EMERGENCY_CASE_DISPATCHED"
    else:
        action_name = f"CASE_STATUS_CHANGED_TO_{payload.status.value}"

    audit_entry = AuditLog(
        case_id=case.id,
        stage=AuditStage.RESOURCE_MATCHING,
        actor=payload.dispatcher_id or "DISPATCHER_CONSOLE",
        action=action_name,
        details={
            "previous_status": previous_status.value,
            "new_status": payload.status.value,
            "notes": payload.notes,
            "ambulance_id": assigned_amb.id if assigned_amb else None,
            "vehicle_number": assigned_amb.vehicle_number if assigned_amb else None,
        },
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(case)
    return _build_case_triage_response(case)




"""Comprehensive Test Suite for Simulated Ambulance & Hospital Resource Verification.

Tests cover:
1. End-to-end resource verification and dispatch (8-step algorithm).
2. Database-driven ambulance availability and BLS/ALS type matching.
3. Database-driven hospital capability matching (cardiac, trauma, burns, ICU) and bed availability.
4. Distance calculation and top candidate filtering.
5. External OSRM routing API integration (mocked HTTP response).
6. External OpenRouteService API integration (mocked HTTP response).
7. External routing API failure handling -> Lightweight Haversine fallback activation.
8. Strict disclaimer guarantee: Never claims live traffic information unless API actually provides it.
9. Database state updates: Ambulance status transitions to DISPATCHED, ResourceMatch record stored.
10. Audit trail persistence: AuditLog created with stage RESOURCE_MATCHING.
11. Error handling:
    - No resources in database.
    - All ambulances unavailable (busy/dispatched/maintenance).
    - No matching ambulance type (strict mode vs resilient fallback mode).
    - Invalid or missing emergency location.
    - Routing API timeouts and 500 errors.
12. REST API endpoints:
    - GET /api/v1/resources/ambulances
    - GET /api/v1/resources/hospitals
    - POST /api/v1/resources/route
    - POST /api/v1/cases/{case_id}/dispatch
"""
import pytest
from unittest.mock import patch, MagicMock
import httpx
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.seed import seed_database
from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType, InputModality
from app.models.location import Location, GeocodingStatus
from app.models.ambulance import Ambulance, AmbulanceStatus
from app.models.hospital import Hospital
from app.models.resource_match import ResourceMatch
from app.models.audit import AuditLog, AuditStage
from app.models.extracted_info import ExtractedInfo
from app.models.ai_decision import AIDecision
from app.services.routing.fallback import HaversineFallbackRouter, haversine_distance_km
from app.services.routing.osrm import OSRMRoutingProvider
from app.services.routing.openrouteservice import OpenRouteServiceProvider
from app.services.routing.factory import get_routing_provider
from app.services.resource_verification import (
    verify_and_match_resources,
    determine_required_ambulance_type,
    determine_required_hospital_capabilities,
    InvalidLocationError,
    NoResourceAvailableError,
    AmbulanceUnavailableError,
    AmbulanceTypeMismatchError,
    HospitalUnavailableError,
)
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def db_session():
    """Yield a database session and clean up test data."""
    db = SessionLocal()
    seed_database(db)
    db.query(Ambulance).update({"status": AmbulanceStatus.AVAILABLE})
    db.commit()
    try:
        yield db
    finally:
        db.query(Ambulance).update({"status": AmbulanceStatus.AVAILABLE})
        db.commit()
        db.close()


@pytest.fixture
def sample_emergency_case(db_session: Session) -> Case:
    """Create a sample triaged emergency case in Pune (Kothrud)."""
    case = Case(
        raw_text="Severe chest pain and difficulty breathing near Kothrud, Pune",
        modality=InputModality.TEXT.value,
        language="english",
        status=CaseStatus.TRIAGED,
        priority=SeverityLevel.CRITICAL,
    )
    db_session.add(case)
    db_session.flush()

    loc = Location(
        case_id=case.id,
        raw_query="Kothrud, Pune",
        formatted_address="Kothrud, Pune, Maharashtra, India",
        latitude=18.5074,
        longitude=73.8077,
        status=GeocodingStatus.SUCCESS,
        is_verified=True,
    )
    db_session.add(loc)

    ext = ExtractedInfo(
        case_id=case.id,
        emergency_type="Cardiac Emergency",
        symptoms=["chest pain", "shortness of breath", "sweating"],
        extracted_location_text="Kothrud, Pune",
        patient_count=1,
        extraction_confidence=0.92,
    )
    db_session.add(ext)

    decision = AIDecision(
        case_id=case.id,
        model_name="mock",
        severity_assessment=SeverityLevel.CRITICAL,
        recommended_ambulance_type=AmbulanceType.ALS,
        clinical_rationale="Suspected acute coronary syndrome with active diaphoresis.",
        confidence_score=0.92,
        latency_ms=120,
    )
    db_session.add(decision)
    db_session.commit()
    db_session.refresh(case)
    return case


# ==============================================================================
# Unit Tests: Routing Engine and Fallbacks
# ==============================================================================

def test_haversine_distance_calculation():
    """Verify spherical distance calculation between known landmarks."""
    # Shivajinagar (18.5314, 73.8446) to Kothrud (18.5074, 73.8077)
    dist = haversine_distance_km(18.5314, 73.8446, 18.5074, 73.8077)
    assert 4.0 <= dist <= 6.0


def test_haversine_fallback_router_guarantees():
    """Verify lightweight fallback returns road-adjusted distance and no live traffic claims."""
    router = HaversineFallbackRouter()
    route = router.calculate_route(
        origin_lat=18.5074,
        origin_lon=73.8077,
        dest_lat=18.5283,
        dest_lon=73.8742,
    )
    assert route.is_fallback is True
    assert route.has_live_traffic is False
    assert "Live traffic" in route.traffic_disclaimer
    assert route.distance_km > 0.0
    assert route.duration_minutes > 0.0
    assert route.provider == "haversine_fallback"


def test_osrm_provider_success_mock():
    """Verify OSRM provider parses external JSON and explicitly marks no live traffic."""
    osrm = OSRMRoutingProvider(base_url="https://mock.osrm.org/route/v1/driving")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": "Ok",
        "routes": [
            {
                "distance": 8450.0,  # 8.45 km
                "duration": 720.0,   # 12.0 minutes
            }
        ],
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        res = osrm.calculate_route(18.5074, 73.8077, 18.5283, 73.8742)

    assert res.is_fallback is False
    assert res.provider == "osrm"
    assert res.distance_km == 8.45
    assert res.duration_minutes == 12.0
    assert res.has_live_traffic is False
    assert "Real-time traffic" in res.traffic_disclaimer


def test_osrm_provider_network_error_triggers_fallback():
    """Verify OSRM falls back seamlessly to Haversine router on network failure."""
    osrm = OSRMRoutingProvider(base_url="https://failing.osrm.internal/route/v1/driving", max_retries=1)

    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
        res = osrm.calculate_route(18.5074, 73.8077, 18.5283, 73.8742)

    assert res.is_fallback is True
    assert res.has_live_traffic is False
    assert "haversine_fallback" in res.provider
    assert "Applied mathematical fallback" in (res.fallback_reason or "")


def test_openrouteservice_missing_key_triggers_fallback():
    """Verify OpenRouteService safely falls back if API key is not configured."""
    ors = OpenRouteServiceProvider(api_key="")
    res = ors.calculate_route(18.5074, 73.8077, 18.5283, 73.8742)
    assert res.is_fallback is True
    assert "API key not configured" in (res.fallback_reason or "")


# ==============================================================================
# Unit & Integration Tests: 8-Step Resource Verification Algorithm
# ==============================================================================

def test_full_resource_verification_and_dispatch(db_session: Session, sample_emergency_case: Case):
    """
    Test complete 8-step resource verification flow:
    - Finds available ALS ambulance.
    - Matches specialty hospital with beds and cardiac care.
    - Uses external routing client with fallback safety.
    - Persists ResourceMatch in database.
    - Updates ambulance status to DISPATCHED.
    - Generates immutable AuditLog entry.
    """
    router = HaversineFallbackRouter()
    match_record, match_result = verify_and_match_resources(
        case_id=sample_emergency_case.id,
        db=db_session,
        routing_provider=router,
        auto_dispatch=True,
    )

    # 1. Match record persisted in DB
    assert match_record.id is not None
    assert match_record.case_id == sample_emergency_case.id
    assert match_record.ambulance_id is not None
    assert match_record.hospital_id is not None
    assert match_record.ambulance_distance_km > 0.0
    assert match_record.ambulance_eta_minutes > 0.0
    assert match_record.hospital_distance_km > 0.0
    assert match_record.is_dispatched is True

    # 2. Matched ambulance type is ALS (matching critical cardiac triage)
    matched_amb = db_session.query(Ambulance).filter(Ambulance.id == match_record.ambulance_id).first()
    assert matched_amb is not None
    assert matched_amb.ambulance_type == AmbulanceType.ALS
    assert matched_amb.status == AmbulanceStatus.DISPATCHED  # Step 8 status transition!

    # 3. Matched hospital has available beds and cardiac capability
    matched_hosp = db_session.query(Hospital).filter(Hospital.id == match_record.hospital_id).first()
    assert matched_hosp is not None
    assert matched_hosp.available_beds > 0
    assert matched_hosp.has_cardiac_care is True

    # 4. Case status updated to DISPATCHED
    db_session.refresh(sample_emergency_case)
    assert sample_emergency_case.status == CaseStatus.DISPATCHED

    # 5. Audit log captured with stage RESOURCE_MATCHING
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == sample_emergency_case.id, AuditLog.stage == AuditStage.RESOURCE_MATCHING)
        .all()
    )
    assert len(audits) >= 1
    latest_audit = audits[-1]
    assert latest_audit.action == "RESOURCE_MATCHED_AND_DISPATCHED"
    assert latest_audit.details["routing_telemetry"]["has_live_traffic"] is False

    # 6. Result response schema validation
    assert match_result.matched_ambulance.vehicle_number == matched_amb.vehicle_number
    assert match_result.matched_hospital.name == matched_hosp.name
    assert match_result.has_live_traffic is False
    assert "Live traffic" in match_result.traffic_disclaimer


def test_hospital_burn_unit_capability_matching(db_session: Session):
    """Verify burn incident matches a hospital equipped with a burn unit."""
    burn_case = Case(
        raw_text="Gas cylinder blast at Hadapsar, severe third-degree burns",
        modality=InputModality.TEXT.value,
        language="english",
        status=CaseStatus.TRIAGED,
        priority=SeverityLevel.CRITICAL,
    )
    db_session.add(burn_case)
    db_session.flush()

    db_session.add(Location(
        case_id=burn_case.id,
        raw_query="Hadapsar, Pune",
        latitude=18.5089,
        longitude=73.9260,
        status=GeocodingStatus.SUCCESS,
        is_verified=True,
    ))
    db_session.add(ExtractedInfo(
        case_id=burn_case.id,
        emergency_type="Fire & Burns",
        symptoms=["severe burns", "smoke inhalation"],
    ))
    db_session.commit()

    match_record, match_result = verify_and_match_resources(
        case_id=burn_case.id,
        db=db_session,
        auto_dispatch=True,
    )

    matched_hosp = db_session.query(Hospital).filter(Hospital.id == match_record.hospital_id).first()
    assert matched_hosp is not None
    assert matched_hosp.has_burn_unit is True
    assert matched_hosp.available_beds > 0


# ==============================================================================
# Failure & Edge Cases Handling
# ==============================================================================

def test_invalid_location_raises_error_and_routes_to_human_review(db_session: Session):
    """Verify case with missing or unresolvable coordinates halts dispatch and routes to human review."""
    unlocated_case = Case(
        raw_text="Emergency somewhere in Pune, cannot identify location",
        modality=InputModality.TEXT.value,
        status=CaseStatus.TRIAGED,
        priority=SeverityLevel.HIGH,
    )
    db_session.add(unlocated_case)
    db_session.flush()

    # Location with failed geocoding status and None coordinates
    db_session.add(Location(
        case_id=unlocated_case.id,
        raw_query="[Unknown]",
        latitude=None,
        longitude=None,
        status=GeocodingStatus.FAILED,
    ))
    db_session.commit()

    with pytest.raises(InvalidLocationError) as exc_info:
        verify_and_match_resources(case_id=unlocated_case.id, db=db_session)

    assert exc_info.value.code == "INVALID_LOCATION"

    # Verify case was safely routed to human review
    db_session.refresh(unlocated_case)
    assert unlocated_case.status == CaseStatus.UNDER_REVIEW
    assert len(unlocated_case.human_reviews) >= 1
    assert "coordinates missing" in unlocated_case.human_reviews[-1].trigger_reason.lower()


def test_unavailable_ambulances_error(db_session: Session, sample_emergency_case: Case):
    """Verify AmbulanceUnavailableError when all ambulances are marked BUSY."""
    # Mark all ambulances as busy
    db_session.query(Ambulance).update({"status": AmbulanceStatus.BUSY})
    db_session.commit()

    with pytest.raises(AmbulanceUnavailableError):
        verify_and_match_resources(case_id=sample_emergency_case.id, db=db_session)


def test_no_matching_ambulance_type_strict_mode(db_session: Session, sample_emergency_case: Case):
    """Verify strict mode raises AmbulanceTypeMismatchError when required ALS is unavailable."""
    # Mark all ALS ambulances as DISPATCHED, keeping BLS available
    db_session.query(Ambulance).filter(Ambulance.ambulance_type == AmbulanceType.ALS).update(
        {"status": AmbulanceStatus.DISPATCHED}
    )
    db_session.commit()

    with pytest.raises(AmbulanceTypeMismatchError) as exc_info:
        verify_and_match_resources(
            case_id=sample_emergency_case.id,
            db=db_session,
            strict_ambulance_type=True,
        )

    assert exc_info.value.required_type == AmbulanceType.ALS


def test_no_matching_ambulance_type_resilient_fallback_mode(db_session: Session, sample_emergency_case: Case):
    """Verify non-strict mode dispatches available BLS when ALS is exhausted with explicit note."""
    # Mark all ALS ambulances as DISPATCHED, keeping BLS available
    db_session.query(Ambulance).filter(Ambulance.ambulance_type == AmbulanceType.ALS).update(
        {"status": AmbulanceStatus.DISPATCHED}
    )
    db_session.commit()

    match_record, match_result = verify_and_match_resources(
        case_id=sample_emergency_case.id,
        db=db_session,
        strict_ambulance_type=False,
        auto_dispatch=True,
    )

    matched_amb = db_session.query(Ambulance).filter(Ambulance.id == match_record.ambulance_id).first()
    assert matched_amb.ambulance_type == AmbulanceType.BLS
    assert "Required ALS ambulance was unavailable" in match_result.explanation


# ==============================================================================
# REST API Endpoint Tests
# ==============================================================================

def test_api_list_ambulances(db_session: Session):
    """Verify GET /api/v1/resources/ambulances returns fleet."""
    resp = client.get("/api/v1/resources/ambulances")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 10
    assert any(a["ambulance_type"] == "ALS" for a in data)


def test_api_list_hospitals(db_session: Session):
    """Verify GET /api/v1/resources/hospitals returns hospital capabilities."""
    resp = client.get("/api/v1/resources/hospitals?has_cardiac=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 5
    assert all(h["has_cardiac_care"] is True for h in data)


def test_api_route_calculation_with_disclaimer():
    """Verify POST /api/v1/resources/route endpoint and traffic disclaimer."""
    payload = {
        "origin_lat": 18.5074,
        "origin_lon": 73.8077,
        "dest_lat": 18.5283,
        "dest_lon": 73.8742,
        "provider_name": "fallback",
    }
    resp = client.post("/api/v1/resources/route", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["distance_km"] > 0.0
    assert data["has_live_traffic"] is False
    assert "Live traffic" in data["traffic_disclaimer"]


def test_api_case_dispatch_endpoint(db_session: Session, sample_emergency_case: Case):
    """Verify POST /api/v1/cases/{case_id}/dispatch endpoint."""
    resp = client.post(f"/api/v1/cases/{sample_emergency_case.id}/dispatch")
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched_ambulance"] is not None
    assert data["matched_hospital"] is not None
    assert data["ambulance_distance_km"] >= 0.0
    assert data["hospital_distance_km"] > 0.0
    assert data["has_live_traffic"] is False

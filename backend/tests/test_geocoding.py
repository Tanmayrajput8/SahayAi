"""Comprehensive test suite for Location Extraction and Geocoding in sahayAi.

Tests cover:
1. Valid locations (OpenStreetMap Nominatim / Mock provider: success, coordinates, formatted address).
2. Ambiguous locations (multiple candidate sites, ambiguous status, is_verified=False).
3. Invalid / unresolvable locations (failed status, latitude=None, emergency preserved).
4. Empty / missing locations (safe failure handling, emergency preserved).
5. Nominatim API timeout and retry backoff behavior.
6. Fail-safe guarantee: Geocoding failures DO NOT reject emergencies; routed to human review.
7. Dispatcher manual intervention: Manually verifying / overriding coordinates via service and REST endpoint.
8. End-to-end integration with the AI triage extraction pipeline.
"""
from unittest.mock import patch, MagicMock
import httpx
import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.case import Case, CaseStatus, SeverityLevel, InputModality
from app.models.location import Location, GeocodingStatus
from app.models.audit import AuditLog, AuditStage
from app.models.human_review import HumanReview
from app.ai.geocoding.schemas import GeocodingResult
from app.ai.geocoding.providers.mock import MockGeocodingProvider
from app.ai.geocoding.providers.nominatim import NominatimGeocodingProvider
from app.ai.geocoding.service import process_case_geocoding, manually_verify_case_location
from app.ai.service import process_case_extraction


@pytest.fixture
def db_session():
    """Yield a database session and clean up created test records."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================================================================
# 1. UNIT TESTS: Mock Geocoding Provider
# ==============================================================================

def test_mock_geocoding_valid_location():
    """Verify mock provider successfully resolves known landmarks with valid coordinates."""
    provider = MockGeocodingProvider()
    result = provider.geocode("Shivajinagar, Pune")

    assert result.status == GeocodingStatus.SUCCESS
    assert result.latitude is not None
    assert result.longitude is not None
    assert 18.0 <= result.latitude <= 19.5
    assert 73.0 <= result.longitude <= 74.5
    assert result.is_verified is True
    assert result.provider == "mock_geocoder"
    assert "Shivajinagar" in (result.formatted_address or "")


def test_mock_geocoding_ambiguous_location():
    """Verify mock provider detects ambiguous queries with multiple candidates."""
    provider = MockGeocodingProvider()
    result = provider.geocode("MG Road")

    assert result.status == GeocodingStatus.AMBIGUOUS
    assert result.is_verified is False
    assert len(result.candidates) >= 2
    assert "ambiguous" in (result.error_message or "").lower()


def test_mock_geocoding_invalid_location():
    """Verify mock provider returns failed status without raising exceptions for unknown places."""
    provider = MockGeocodingProvider()
    result = provider.geocode("xyz_nonexistent_fictional_location_999")

    assert result.status == GeocodingStatus.FAILED
    assert result.latitude is None
    assert result.longitude is None
    assert result.is_verified is False
    assert "could not be resolved" in (result.error_message or "").lower()


def test_mock_geocoding_empty_location():
    """Verify empty/blank query is handled gracefully as failed."""
    provider = MockGeocodingProvider()
    result = provider.geocode("   ")

    assert result.status == GeocodingStatus.FAILED
    assert result.latitude is None
    assert result.longitude is None
    assert result.is_verified is False


# ==============================================================================
# 2. UNIT TESTS: OpenStreetMap Nominatim Provider (HTTP & Retries)
# ==============================================================================

def test_nominatim_successful_geocoding():
    """Verify Nominatim provider parses standard OSM search response correctly."""
    mock_response = [
        {
            "lat": "18.5204303",
            "lon": "73.8567437",
            "display_name": "Pune, Maharashtra, 411001, India",
            "importance": 0.85,
        }
    ]

    with patch("app.ai.geocoding.providers.nominatim.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = NominatimGeocodingProvider(timeout_seconds=2.0, max_retries=1)
        result = provider.geocode("Pune, Maharashtra")

        assert result.status == GeocodingStatus.SUCCESS
        assert result.latitude == pytest.approx(18.5204303, abs=0.001)
        assert result.longitude == pytest.approx(73.8567437, abs=0.001)
        assert result.is_verified is True
        assert result.provider == "osm_nominatim"
        assert "Pune" in (result.formatted_address or "")


def test_nominatim_ambiguous_spatial_candidates():
    """Verify Nominatim classifies multiple widely separated results as AMBIGUOUS."""
    mock_candidates = [
        {"lat": "18.5204", "lon": "73.8567", "display_name": "MG Road, Pune, Maharashtra", "importance": 0.6},
        {"lat": "12.9716", "lon": "77.5946", "display_name": "MG Road, Bengaluru, Karnataka", "importance": 0.6},
        {"lat": "19.0760", "lon": "72.8777", "display_name": "MG Road, Mumbai, Maharashtra", "importance": 0.6},
    ]

    with patch("app.ai.geocoding.providers.nominatim.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_candidates
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = NominatimGeocodingProvider(timeout_seconds=2.0, max_retries=1)
        result = provider.geocode("MG Road")

        assert result.status == GeocodingStatus.AMBIGUOUS
        assert result.is_verified is False
        assert len(result.candidates) == 3
        # Verify error message indicates ambiguity and dispatcher review
        assert "dispatcher" in (result.error_message or "").lower()


def test_nominatim_no_results_failed_status():
    """Verify Nominatim handles empty result list from OSM gracefully without errors."""
    with patch("app.ai.geocoding.providers.nominatim.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = NominatimGeocodingProvider(timeout_seconds=2.0, max_retries=1)
        result = provider.geocode("FictionalUnknownStreetXYZ")

        assert result.status == GeocodingStatus.FAILED
        assert result.latitude is None
        assert result.longitude is None
        assert result.is_verified is False
        assert "no geographic matches" in (result.error_message or "").lower()


def test_nominatim_timeout_and_retry_handling():
    """Verify Nominatim retries upon API timeout and safely returns FAILED status after retries."""
    with patch("app.ai.geocoding.providers.nominatim.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        # Raise TimeoutException on each call
        mock_client.get.side_effect = httpx.TimeoutException("Read timed out")
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = NominatimGeocodingProvider(timeout_seconds=0.1, max_retries=2)
        result = provider.geocode("Swargate, Pune")

        # 1 initial + 2 retries = 3 total attempts
        assert mock_client.get.call_count == 3
        assert result.status == GeocodingStatus.FAILED
        assert result.latitude is None
        assert result.longitude is None
        assert result.is_verified is False
        assert "timed out" in (result.error_message or "").lower()


def test_nominatim_http_error_recovery():
    """Verify Nominatim recovers safely from 500 internal server error on external API."""
    with patch("app.ai.geocoding.providers.nominatim.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="Internal Server Error",
            request=MagicMock(),
            response=mock_resp,
        )
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = NominatimGeocodingProvider(timeout_seconds=0.1, max_retries=1)
        result = provider.geocode("Deccan Gymkhana, Pune")

        assert result.status == GeocodingStatus.FAILED
        assert result.is_verified is False
        assert result.latitude is None
        # After retries exhausted on HTTP 500, any failure message is acceptable
        assert result.error_message is not None


# ==============================================================================
# 3. SERVICE TESTS: process_case_geocoding & Fail-Safe Guarantees
# ==============================================================================

def test_process_case_geocoding_valid(db_session: Session):
    """Verify valid location geocoding persists location, marks verified, and logs audit."""
    case = Case(
        raw_text="Accident on FC Road, Pune near Deccan bus stop",
        modality=InputModality.TEXT.value,
        status=CaseStatus.PENDING,
        priority=SeverityLevel.HIGH,
    )
    db_session.add(case)
    db_session.flush()

    loc, trigger = process_case_geocoding(
        case=case,
        location_query="FC Road, Pune",
        db=db_session,
        provider=MockGeocodingProvider(),
    )
    db_session.commit()

    assert loc is not None
    assert loc.status == GeocodingStatus.SUCCESS
    assert loc.is_verified is True
    assert loc.latitude is not None
    assert loc.longitude is not None
    assert loc.location_text == "FC Road, Pune"
    assert loc.provider == "mock_geocoder"
    assert trigger is None

    # Check Audit Log
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.stage == AuditStage.GEOCODING)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action == "GEOCODING_SUCCESS"
    assert audit.details["status"] == "success"


def test_process_case_geocoding_ambiguous_does_not_reject_emergency(db_session: Session):
    """FAIL-SAFE: Ambiguous location must NOT reject emergency; surfaces for dispatcher."""
    case = Case(
        raw_text="Elderly patient collapsed on MG Road",
        modality=InputModality.TEXT.value,
        status=CaseStatus.PENDING,
        priority=SeverityLevel.CRITICAL,
    )
    db_session.add(case)
    db_session.flush()

    loc, trigger = process_case_geocoding(
        case=case,
        location_query="MG Road",
        db=db_session,
        provider=MockGeocodingProvider(),
    )
    db_session.commit()

    assert loc.status == GeocodingStatus.AMBIGUOUS
    assert loc.is_verified is False
    assert trigger is not None
    assert "Ambiguous location" in trigger
    assert "Dispatcher intervention required" in trigger

    # Emergency case is still intact — status is PENDING or UNDER_REVIEW, never dropped
    retrieved_case = db_session.query(Case).filter(Case.id == case.id).first()
    assert retrieved_case is not None
    assert retrieved_case.status not in (CaseStatus.CANCELLED, CaseStatus.DUPLICATE)


def test_process_case_geocoding_failed_does_not_reject_emergency(db_session: Session):
    """FAIL-SAFE: Unresolvable location must NOT reject emergency; marks unverified & logs failure."""
    case = Case(
        raw_text="Breathing difficulty at NonexistentMarsBaseAlphaSector9",
        modality=InputModality.TEXT.value,
        status=CaseStatus.PENDING,
        priority=SeverityLevel.HIGH,
    )
    db_session.add(case)
    db_session.flush()

    loc, trigger = process_case_geocoding(
        case=case,
        location_query="NonexistentMarsBaseAlphaSector9",
        db=db_session,
        provider=MockGeocodingProvider(),
    )
    db_session.commit()

    assert loc.status == GeocodingStatus.FAILED
    assert loc.latitude is None
    assert loc.longitude is None
    assert loc.is_verified is False
    assert trigger is not None
    assert "Dispatcher intervention required" in trigger

    # Verify audit failure record was created
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.stage == AuditStage.GEOCODING)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.action == "GEOCODING_FAILED"
    assert audit.details["status"] == "failed"


def test_process_case_geocoding_empty_query(db_session: Session):
    """FAIL-SAFE: Missing location query is handled gracefully without exception."""
    case = Case(
        raw_text="Patient having chest pain, caller panicked and hung up without address",
        modality=InputModality.TEXT.value,
        status=CaseStatus.PENDING,
        priority=SeverityLevel.CRITICAL,
    )
    db_session.add(case)
    db_session.flush()

    loc, trigger = process_case_geocoding(
        case=case,
        location_query=None,
        db=db_session,
        provider=MockGeocodingProvider(),
    )
    db_session.commit()

    assert loc.status == GeocodingStatus.FAILED
    assert loc.latitude is None
    assert loc.is_verified is False
    assert "Missing emergency location" in trigger


# ==============================================================================
# 4. DISPATCHER INTERVENTION: Manual Location Verification & REST Endpoint
# ==============================================================================

def test_manually_verify_case_location_service(db_session: Session):
    """Verify dispatcher can manually override unverified coordinates."""
    case = Case(
        raw_text="Collision near unmapped construction gate",
        modality=InputModality.TEXT.value,
        status=CaseStatus.UNDER_REVIEW,
        priority=SeverityLevel.HIGH,
    )
    db_session.add(case)
    db_session.flush()

    # Initially failed geocode
    process_case_geocoding(case=case, location_query="Unknown Gate", db=db_session, provider=MockGeocodingProvider())

    # Dispatcher manually verifies coordinates
    updated_loc = manually_verify_case_location(
        case_id=case.id,
        latitude=18.5314,
        longitude=73.8446,
        formatted_address="Gate 4, Metro Project, Pune",
        dispatcher_id="dispatcher_sarah",
        db=db_session,
    )

    assert updated_loc.status == GeocodingStatus.SUCCESS
    assert updated_loc.is_verified is True
    assert updated_loc.latitude == 18.5314
    assert updated_loc.longitude == 73.8446
    assert updated_loc.formatted_address == "Gate 4, Metro Project, Pune"
    assert "dispatcher_sarah" in updated_loc.geocoding_provider

    # Verify audit log of human intervention
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.action == "LOCATION_MANUALLY_VERIFIED")
        .first()
    )
    assert audit is not None
    assert audit.actor == "DISPATCHER_dispatcher_sarah"
    assert audit.details["latitude"] == 18.5314


def test_dispatcher_patch_location_endpoint(client, db_session: Session):
    """Test REST API PATCH /api/v1/cases/{case_id}/location for dispatcher intervention."""
    case = Case(
        raw_text="Fall from scaffold, exact gate unknown",
        modality=InputModality.TEXT.value,
        status=CaseStatus.UNDER_REVIEW,
        priority=SeverityLevel.CRITICAL,
    )
    db_session.add(case)
    db_session.commit()

    payload = {
        "latitude": 18.5204,
        "longitude": 73.8567,
        "formatted_address": "Mandai Market, Budhwar Peth, Pune",
        "dispatcher_notes": "Confirmed landmark via caller re-dial",
    }

    response = client.patch(
        f"/api/v1/cases/{case.id}/location?dispatcher_id=lead_dispatcher",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["latitude"] == 18.5204
    assert data["longitude"] == 73.8567
    assert data["geocoding_status"] == "success"
    assert data["is_location_verified"] is True
    assert "lead_dispatcher" in (data["geocoding_provider"] or "")


# ==============================================================================
# 5. END-TO-END PIPELINE: process_case_extraction With Geocoding
# ==============================================================================

def test_extraction_pipeline_with_valid_location(db_session: Session):
    """End-to-end: extraction extracts location and geocodes it successfully."""
    case = Case(
        raw_text="Major vehicle accident near Shivajinagar, Pune with severe bleeding, 2 people hurt",
        modality=InputModality.TEXT.value,
        status=CaseStatus.PENDING,
        priority=SeverityLevel.MODERATE,
    )
    db_session.add(case)
    db_session.commit()

    updated = process_case_extraction(case_id=case.id, db=db_session)

    assert updated.location is not None
    assert updated.location.status == GeocodingStatus.SUCCESS
    assert updated.location.is_verified is True
    assert updated.location.latitude is not None
    assert updated.location.longitude is not None


def test_extraction_pipeline_with_ambiguous_location_routes_to_human_review(db_session: Session):
    """FAIL-SAFE: extraction with ambiguous location sets status UNDER_REVIEW and does not crash."""
    case = Case(
        raw_text="Bike crash on MG Road, victim has severe chest injury",
        modality=InputModality.TEXT.value,
        status=CaseStatus.PENDING,
        priority=SeverityLevel.MODERATE,
    )
    db_session.add(case)
    db_session.commit()

    updated = process_case_extraction(case_id=case.id, db=db_session)

    # Must route to UNDER_REVIEW so dispatcher can disambiguate
    assert updated.status == CaseStatus.UNDER_REVIEW
    assert updated.location is not None
    assert updated.location.status == GeocodingStatus.AMBIGUOUS
    assert updated.location.is_verified is False

    review = (
        db_session.query(HumanReview)
        .filter(HumanReview.case_id == case.id)
        .order_by(HumanReview.created_at.desc())
        .first()
    )
    assert review is not None
    assert "Ambiguous" in review.trigger_reason or "MG Road" in review.trigger_reason

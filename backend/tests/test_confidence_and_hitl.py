"""Unit and API integration tests for Multi-Signal Confidence Scoring and Human-in-the-Loop review."""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType, InputModality
from app.models.ai_decision import AIDecision
from app.models.extracted_info import ExtractedInfo
from app.models.location import Location
from app.models.human_review import HumanReview, ReviewStatus
from app.services.confidence_scoring import calculate_system_confidence
from app.services.human_review import submit_human_review


def test_confidence_calculation_weights_and_thresholds(client: TestClient):
    """Test 6-component weighted calculation and categorization (HIGH, MEDIUM, LOW)."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        case = Case(
            caller_phone="9988776655",
            raw_text="Severe chest pain and sweating near Swargate Pune",
            modality=InputModality.TEXT.value,
            language="english",
            status=CaseStatus.PENDING,
            priority=SeverityLevel.CRITICAL,
        )
        db.add(case)
        db.flush()

        # Add signals
        ext = ExtractedInfo(
            case_id=case.id,
            emergency_type="cardiac",
            symptoms=["chest pain", "sweating"],
            extracted_location_text="Swargate Pune",
            patient_count=1,
        )
        loc = Location(
            case_id=case.id,
            raw_query="Swargate Pune",
            latitude=18.5018,
            longitude=73.8636,
            status="success",
            confidence=0.95,
            is_verified=True,
        )
        dec = AIDecision(
            case_id=case.id,
            model_name="mock",
            severity_assessment=SeverityLevel.CRITICAL,
            recommended_ambulance_type=AmbulanceType.ALS,
            clinical_rationale="Cardiac emergency suspected.",
            confidence_score=0.9,
            ai_suggested_severity="CRITICAL",
            ai_suggested_ambulance="ALS",
            deterministic_severity="CRITICAL",
            deterministic_ambulance="ALS",
            has_conflict=False,
        )
        db.add_all([ext, loc, dec])
        db.commit()

        breakdown = calculate_system_confidence(case, db)
        assert breakdown.overall_confidence >= 0.75
        assert breakdown.confidence_level == "HIGH"
        assert breakdown.components["extraction_completeness"] == 1.0
        assert breakdown.components["rule_llm_agreement"] == 1.0
        assert breakdown.components["location_verification"] == 1.0
    finally:
        db.close()


def test_low_confidence_routes_to_human_review(client: TestClient):
    """Test that a case with missing location and conflicting rules drops to LOW confidence."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        case = Case(
            caller_phone="9988776655",
            raw_text="Unknown problem somewhere",
            modality=InputModality.TEXT.value,
            language="english",
            status=CaseStatus.PENDING,
            priority=SeverityLevel.UNKNOWN,
        )
        db.add(case)
        db.flush()

        ext = ExtractedInfo(case_id=case.id, emergency_type="unknown", symptoms=[], extracted_location_text=None)
        loc = Location(case_id=case.id, raw_query="unknown", status="failed", confidence=0.0)
        dec = AIDecision(
            case_id=case.id,
            severity_assessment=SeverityLevel.HIGH,
            recommended_ambulance_type=AmbulanceType.ALS,
            clinical_rationale="Incomplete input",
            confidence_score=0.3,
            ai_suggested_severity="HIGH",
            deterministic_severity="UNKNOWN",
            has_conflict=True,
        )
        db.add_all([ext, loc, dec])
        db.commit()

        breakdown = calculate_system_confidence(case, db)
        assert breakdown.overall_confidence < 0.50
        assert breakdown.confidence_level == "LOW"
    finally:
        db.close()


def test_human_review_workflow_and_original_decision_preservation(client: TestClient):
    """Test human dispatcher modification while preserving original AI decision snapshot."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        case = Case(
            caller_phone="9988112233",
            raw_text="Mild fever and body pain in Kothrud",
            modality=InputModality.TEXT.value,
            status=CaseStatus.UNDER_REVIEW,
            priority=SeverityLevel.HIGH,
        )
        db.add(case)
        db.flush()

        dec = AIDecision(
            case_id=case.id,
            severity_assessment=SeverityLevel.HIGH,
            recommended_ambulance_type=AmbulanceType.ALS,
            clinical_rationale="AI suggested high severity.",
            confidence_score=0.45,
        )
        db.add(dec)
        db.commit()

        # Dispatcher modifies priority to MODERATE and ambulance to BLS
        updated_case, review = submit_human_review(
            case_id=case.id,
            action="MODIFY",
            db=db,
            dispatcher_id="dispatcher_pune_1",
            modified_severity=SeverityLevel.MODERATE,
            modified_ambulance=AmbulanceType.BLS,
            dispatcher_notes="Patient vitals stable, triage downgraded to moderate.",
        )

        assert updated_case.priority == SeverityLevel.MODERATE
        assert updated_case.status == CaseStatus.TRIAGED
        assert review.review_status == ReviewStatus.OVERRIDDEN

        # Original decision must remain preserved
        assert review.original_decision["severity"] == "HIGH"
        assert review.original_decision["ambulance_type"] == "ALS"
        assert review.final_decision["modified_severity"] == "MODERATE"
        assert review.final_decision["modified_ambulance"] == "BLS"
    finally:
        db.close()


def test_api_review_queue_and_submit_endpoints(client: TestClient):
    """Test GET /api/v1/review/queue and POST /api/v1/review/{case_id}/submit endpoints."""
    # Create a case under review
    create_resp = client.post(
        "/api/v1/cases",
        json={"raw_text": "Vague pain in Shivaji Nagar", "caller_phone": "9876543210"},
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    # Mark as under review
    from app.db.session import SessionLocal
    db = SessionLocal()
    c = db.query(Case).filter(Case.id == case_id).first()
    c.status = CaseStatus.UNDER_REVIEW
    rev = HumanReview(
        case_id=case_id,
        trigger_reason="Test review flag",
        original_decision={"severity": "MODERATE", "ambulance": "BLS"},
    )
    db.add(rev)
    db.commit()
    db.close()

    # Query queue
    q_resp = client.get("/api/v1/review/queue")
    assert q_resp.status_code == 200
    queue = q_resp.json()
    assert any(item["case_id"] == case_id for item in queue)

    # Submit APPROVE decision
    sub_resp = client.post(
        f"/api/v1/review/{case_id}/submit",
        json={"action": "APPROVE", "dispatcher_id": "disp_01", "dispatcher_notes": "Looks good"},
    )
    assert sub_resp.status_code == 200
    data = sub_resp.json()
    assert data["review_status"] == "APPROVED"
    assert data["case_status"] == "TRIAGED"

"""
Tests for Hybrid Triage: Severity and Ambulance-Type Recommendation Engine.

Requirements verified:
- Hybrid logic: LLM free-text understanding + Deterministic rule validation
- Prototype categories: Critical, High, Moderate, Low, Unknown
- Prototype mapping:
    Critical → ALS
    High → ALS
    Moderate → BLS
    Low → BLS
    Unknown → ALS + mandatory human review
- Clearly labeled as a prototype decision-support heuristic (NOT clinically validated triage)
- Edge case handling:
    * missing symptoms
    * contradictory symptoms
    * multiple patients (MCI escalation)
    * unknown emergency
    * vague emergency
    * conflicting LLM / rule output (safety override)
- Dual storage: Both AI result and deterministic result stored for auditing in AIDecision and AuditLog
"""
import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType
from app.models.ai_decision import AIDecision
from app.models.audit import AuditLog, AuditStage
from app.ai.schemas import EmergencyExtractionResult
from app.ai.providers.base import LLMProvider
from app.ai.service import process_case_extraction
from app.ai.triage_engine import (
    evaluate_hybrid_triage,
    PROTOTYPE_DISCLAIMER,
    DECISION_TYPE_HEURISTIC,
    PROTOTYPE_AMBULANCE_MAP,
)


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session


def _create_case(db: Session, raw_text: str) -> Case:
    case = Case(
        raw_text=raw_text,
        modality="text",
        status=CaseStatus.PENDING,
        priority=SeverityLevel.MODERATE,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


# ===========================================================================
# 1. Prototype Mapping Tests (Critical, High, Moderate, Low, Unknown)
# ===========================================================================

def test_prototype_category_mapping_critical_to_als():
    """Critical severity must map to ALS."""
    extraction = EmergencyExtractionResult(
        emergency_type="Cardiac Emergency",
        symptoms=["cardiac arrest", "unconscious"],
        location="Swargate",
        severity=SeverityLevel.CRITICAL,
        ambulance_requirement=AmbulanceType.ALS,
        clinical_rationale="Cardiac arrest requires immediate ALS.",
    )
    res = evaluate_hybrid_triage(extraction, "Cardiac arrest at Swargate")
    assert res.final_severity == SeverityLevel.CRITICAL
    assert res.final_ambulance == AmbulanceType.ALS
    assert PROTOTYPE_AMBULANCE_MAP[SeverityLevel.CRITICAL] == AmbulanceType.ALS


def test_prototype_category_mapping_high_to_als():
    """High severity must map to ALS."""
    extraction = EmergencyExtractionResult(
        emergency_type="Trauma",
        symptoms=["compound leg fracture", "moderate bleeding"],
        location="Marine Drive",
        severity=SeverityLevel.HIGH,
        ambulance_requirement=AmbulanceType.ALS,
        clinical_rationale="High acuity trauma with potential for hemodynamic compromise.",
    )
    res = evaluate_hybrid_triage(extraction, "Accident at Marine Drive, broken bone")
    assert res.final_severity == SeverityLevel.HIGH
    assert res.final_ambulance == AmbulanceType.ALS
    assert PROTOTYPE_AMBULANCE_MAP[SeverityLevel.HIGH] == AmbulanceType.ALS


def test_prototype_category_mapping_moderate_to_bls():
    """Moderate severity must map to BLS."""
    extraction = EmergencyExtractionResult(
        emergency_type="General Medical Emergency",
        symptoms=["sprained ankle", "mild swelling"],
        location="Dadar",
        severity=SeverityLevel.MODERATE,
        ambulance_requirement=AmbulanceType.BLS,
        clinical_rationale="Isolated sprain with stable airway and vitals.",
    )
    res = evaluate_hybrid_triage(extraction, "Sprained ankle at Dadar station, needs assistance")
    assert res.final_severity == SeverityLevel.MODERATE
    assert res.final_ambulance == AmbulanceType.BLS
    assert PROTOTYPE_AMBULANCE_MAP[SeverityLevel.MODERATE] == AmbulanceType.BLS


def test_prototype_category_mapping_low_to_bls():
    """Low severity must map to BLS."""
    extraction = EmergencyExtractionResult(
        emergency_type="General Medical Emergency",
        symptoms=["minor scrape", "finger cut"],
        location="Andheri",
        severity=SeverityLevel.LOW,
        ambulance_requirement=AmbulanceType.BLS,
        clinical_rationale="Minor superficial laceration.",
    )
    res = evaluate_hybrid_triage(extraction, "Small paper cut at Andheri")
    assert res.final_severity == SeverityLevel.LOW
    assert res.final_ambulance == AmbulanceType.BLS
    assert PROTOTYPE_AMBULANCE_MAP[SeverityLevel.LOW] == AmbulanceType.BLS


def test_prototype_category_mapping_unknown_to_unknown_and_mandatory_review():
    """Unknown severity must map to UNKNOWN + mandatory human review (UNKNOWN MUST NOT become ALS)."""
    extraction = EmergencyExtractionResult(
        emergency_type="Unknown",
        symptoms=[],
        location="Unknown",
        severity=SeverityLevel.UNKNOWN,
        ambulance_requirement=AmbulanceType.UNKNOWN,
        clinical_rationale="Unclassifiable emergency.",
    )
    res = evaluate_hybrid_triage(extraction, "Something is happening here!")
    assert res.final_severity == SeverityLevel.UNKNOWN
    assert res.final_ambulance == AmbulanceType.UNKNOWN
    assert res.mandatory_human_review is True
    assert PROTOTYPE_AMBULANCE_MAP[SeverityLevel.UNKNOWN] == AmbulanceType.UNKNOWN



# ===========================================================================
# 2. Prototype Disclaimer & Labeling Verification
# ===========================================================================

def test_prototype_disclaimer_and_labeling():
    """
    IMPORTANT REQUIREMENT:
    Clearly label this as a prototype decision-support heuristic.
    Do NOT call it clinically validated triage.
    """
    extraction = EmergencyExtractionResult(
        emergency_type="Cardiac Emergency",
        symptoms=["chest pain"],
        severity=SeverityLevel.CRITICAL,
        ambulance_requirement=AmbulanceType.ALS,
    )
    res = evaluate_hybrid_triage(extraction, "Chest pain call")
    assert "PROTOTYPE DECISION-SUPPORT HEURISTIC" in res.disclaimer
    assert "NOT clinically validated triage" in res.disclaimer
    assert res.decision_type == DECISION_TYPE_HEURISTIC
    assert PROTOTYPE_DISCLAIMER in res.clinical_rationale


# ===========================================================================
# 3. Edge Case Handling Tests
# ===========================================================================

def test_handle_missing_symptoms():
    """When symptoms are completely missing, rule engine assigns UNKNOWN + UNKNOWN + review."""
    extraction = EmergencyExtractionResult(
        emergency_type="General Medical Emergency",
        symptoms=[],  # Missing symptoms
        location="Dadar",
        severity=SeverityLevel.MODERATE,
        ambulance_requirement=AmbulanceType.BLS,
    )
    res = evaluate_hybrid_triage(extraction, "Send ambulance to Dadar station immediately!")
    assert res.final_severity == SeverityLevel.UNKNOWN
    assert res.final_ambulance == AmbulanceType.UNKNOWN
    assert res.mandatory_human_review is True
    assert any("No clinical symptoms" in t for t in res.review_triggers)


def test_handle_contradictory_symptoms():
    """Contradictory symptoms trigger safety elevation, conflict flag, and review."""
    extraction = EmergencyExtractionResult(
        emergency_type="Trauma",
        symptoms=["dead", "walking fine"],
        is_contradictory=True,
        contradiction_notes="Caller says patient is dead but walking fine.",
        severity=SeverityLevel.LOW,
        ambulance_requirement=AmbulanceType.BLS,
    )
    res = evaluate_hybrid_triage(extraction, "The patient is totally dead but walking fine.")
    # Safe failure mode elevates to HIGH/CRITICAL and ALS
    assert res.final_severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)
    assert res.final_ambulance == AmbulanceType.ALS
    assert res.mandatory_human_review is True
    assert res.has_conflict is True


def test_handle_multiple_patients():
    """Multi-patient incidents (patient_count >= 2) must trigger MCI rule and ALS assignment."""
    extraction = EmergencyExtractionResult(
        emergency_type="Road Traffic Accident",
        symptoms=["abrasions", "bruises"],
        patient_count=4,  # Multiple patients
        severity=SeverityLevel.MODERATE,  # LLM thought moderate
        ambulance_requirement=AmbulanceType.BLS,
    )
    res = evaluate_hybrid_triage(extraction, "Bus collision near Kurla, 4 people injured")
    assert res.is_multi_patient is True
    assert res.patient_count == 4
    # Multi-casualty rule escalates to CRITICAL/HIGH and ALS
    assert res.final_severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)
    assert res.final_ambulance == AmbulanceType.ALS
    assert res.has_conflict is True  # Discrepancy with LLM's MODERATE/BLS


def test_handle_unknown_emergency():
    """Unknown emergency type must map to UNKNOWN + UNKNOWN + mandatory human review."""
    extraction = EmergencyExtractionResult(
        emergency_type="Unknown",
        symptoms=[],
        severity=SeverityLevel.UNKNOWN,
        ambulance_requirement=AmbulanceType.UNKNOWN,
    )
    res = evaluate_hybrid_triage(extraction, "Unknown emergency reported")
    assert res.final_severity == SeverityLevel.UNKNOWN
    assert res.final_ambulance == AmbulanceType.UNKNOWN
    assert res.mandatory_human_review is True


def test_handle_vague_emergency():
    """Short vague emergency calls without clinical signs map to UNKNOWN + UNKNOWN."""
    extraction = EmergencyExtractionResult(
        emergency_type="General Medical Emergency",
        symptoms=["reported distress"],
        severity=SeverityLevel.MODERATE,
        ambulance_requirement=AmbulanceType.BLS,
    )
    res = evaluate_hybrid_triage(extraction, "Please help quickly")
    assert res.final_severity == SeverityLevel.UNKNOWN
    assert res.final_ambulance == AmbulanceType.UNKNOWN
    assert res.mandatory_human_review is True



def test_handle_conflicting_llm_rule_output():
    """
    Deterministic rule overrides unsafe LLM suggestion:
    If LLM suggests LOW/BLS for acute chest pain/cardiac symptoms,
    deterministic rule overrides to CRITICAL + ALS and flags conflict.
    """
    extraction = EmergencyExtractionResult(
        emergency_type="General Medical Emergency",
        symptoms=["chest pain", "shortness of breath"],
        severity=SeverityLevel.LOW,  # Erroneous unsafe LLM suggestion
        ambulance_requirement=AmbulanceType.BLS,
        clinical_rationale="Under-triage by LLM.",
    )
    res = evaluate_hybrid_triage(extraction, "Severe acute chest pain and shortness of breath")
    # Rule engine overrides unsafe LOW to CRITICAL and BLS to ALS
    assert res.final_severity == SeverityLevel.CRITICAL
    assert res.final_ambulance == AmbulanceType.ALS
    assert res.has_conflict is True
    assert res.conflict_reason is not None
    assert "Discrepancy" in res.conflict_reason
    assert res.mandatory_human_review is True


# ===========================================================================
# 4. Dual Storage for Auditing (AIDecision & AuditLog)
# ===========================================================================

def test_dual_audit_storage_in_ai_decision_and_audit_log(db_session):
    """
    Verify that process_case_extraction stores:
    1. Both AI suggestion and deterministic validation in AIDecision table
    2. Side-by-side comparison in AuditLog (AI_EXTRACTION stage)
    3. Prototype disclaimer in both records
    """
    class TestProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "mock_test_vendor"

        def extract_emergency_info(self, raw_text: str, modality: str = "text", context=None):
            # Intentionally return MODERATE/BLS for a multi-patient cardiac event to test hybrid dual recording
            return EmergencyExtractionResult(
                emergency_type="Cardiac Emergency",
                symptoms=["chest pain", "sweating"],
                location="Marine Drive",
                severity=SeverityLevel.MODERATE,
                ambulance_requirement=AmbulanceType.BLS,
                patient_count=3,
                confidence_score=0.82,
                clinical_rationale="Initial AI suggestions.",
            )

    case = _create_case(db_session, "3 people collapsed with chest pain at Marine Drive")
    updated = process_case_extraction(case.id, db_session, provider=TestProvider())

    # 1. Verify AIDecision record
    decision: AIDecision = updated.ai_decisions[-1]
    assert decision is not None
    assert decision.ai_suggested_severity == "MODERATE"
    assert decision.ai_suggested_ambulance == "BLS"
    assert decision.deterministic_severity in ("HIGH", "CRITICAL")
    assert decision.deterministic_ambulance == "ALS"
    assert decision.has_conflict is True
    assert decision.conflict_reason is not None
    assert "PROTOTYPE DECISION-SUPPORT HEURISTIC" in decision.disclaimer
    assert "not clinically validated triage" in decision.disclaimer.lower()

    # 2. Verify AuditLog record
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.stage == AuditStage.AI_EXTRACTION)
        .first()
    )
    assert audit is not None
    details = audit.details
    assert "ai_suggestion" in details
    assert details["ai_suggestion"]["severity"] == "MODERATE"
    assert details["ai_suggestion"]["ambulance"] == "BLS"
    assert "deterministic_validation" in details
    assert details["deterministic_validation"]["has_conflict"] is True
    assert details["deterministic_validation"]["ambulance"] == "ALS"
    assert "disclaimer" in details
    assert "PROTOTYPE DECISION-SUPPORT HEURISTIC" in details["disclaimer"]


# ===========================================================================
# 5. REST API Hybrid Triage Response Inspection
# ===========================================================================

def test_api_triage_returns_hybrid_fields_and_disclaimer(client):
    """Test that POST /api/v1/cases/{case_id}/triage exposes hybrid auditing and disclaimer."""
    created = client.post(
        "/api/v1/cases",
        json={"raw_input": "Cardiac collapse at Swargate, caller in shock"},
    ).json()
    case_id = created["id"]

    r = client.post(f"/api/v1/cases/{case_id}/triage")
    assert r.status_code == 200
    data = r.json()

    assert data["priority"] == "CRITICAL"
    assert data["recommended_ambulance"] == "ALS"
    assert "PROTOTYPE DECISION-SUPPORT HEURISTIC" in data["disclaimer"]
    assert "NOT clinically validated triage" in data["disclaimer"]
    assert data["deterministic_severity"] is not None
    assert data["deterministic_ambulance"] is not None

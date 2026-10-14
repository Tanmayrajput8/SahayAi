"""
Tests for the LLM Intelligence Layer (SahayAI Emergency).

Requirements verified:
- English
- Hindi (Devanagari)
- Marathi (Devanagari)
- Code-mixed language (Hinglish & Marathish)
- Typos and slang
- Panic phrasing
- Missing location (flagged in missing_information and routed to review)
- Contradictory input (flagged and confidence reduced)
- LLM timeout fail-safe (case NOT lost, routed to human review)
- LLM API failure fail-safe (case NOT lost, routed to human review)
- Malformed JSON recovery and unrecoverable fail-safe
- Provider independence (pluggable LLMProvider)
- REST API integration: POST /api/v1/cases/{case_id}/triage
"""
import pytest
from unittest.mock import patch, MagicMock
import httpx
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType
from app.models.extracted_info import ExtractedInfo
from app.models.human_review import HumanReview, ReviewStatus
from app.models.audit import AuditLog, AuditStage
from app.ai.providers.base import LLMProvider
from app.ai.providers.grok import GrokProvider
from app.ai.providers.mock import MockProvider
from app.ai.schemas import EmergencyExtractionResult
from app.ai.json_utils import parse_and_validate_extraction
from app.ai.exceptions import LLMOutputFormatError, LLMTimeoutError, LLMAPIError
from app.ai.service import process_case_extraction


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session


def _create_test_case(db: Session, raw_text: str) -> Case:
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
# 1. Multi-lingual Extraction Tests
# ===========================================================================

def test_extraction_english():
    """Standard English input extraction."""
    provider = MockProvider()
    result = provider.extract_emergency_info(
        "Severe cardiac chest pain at Swargate depot, patient collapsed and unconscious"
    )
    assert result.emergency_type == "Cardiac Emergency"
    assert result.severity == SeverityLevel.CRITICAL
    assert result.ambulance_requirement == AmbulanceType.ALS
    assert result.detected_language == "English"
    assert result.location == "Swargate"
    assert result.conscious_status == "unconscious"
    assert result.confidence_score >= 0.75


def test_extraction_hindi():
    """Hindi input in Devanagari script."""
    provider = MockProvider()
    result = provider.extract_emergency_info(
        "यहाँ अंधेरी स्टेशन के पास एक्सीडेंट हुआ है बहुत खून बह रहा है जल्दी मदद भेजो"
    )
    assert result.detected_language == "Hindi"
    assert result.emergency_type == "Road Traffic Accident"
    assert "अंधेरी" in result.location
    assert any("bleeding" in s or "hemorrhage" in s for s in result.symptoms)
    assert result.severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)


def test_extraction_marathi():
    """Marathi input in Devanagari script."""
    provider = MockProvider()
    result = provider.extract_emergency_info(
        "दादर स्टेशन जवळ एक व्यक्ती बेशुद्ध पडली आहे, श्वास घ्यायला प्रचंड त्रास होतोय"
    )
    assert result.detected_language == "Marathi"
    assert "दादर" in result.location
    assert result.conscious_status == "unconscious"
    assert result.breathing_status == "difficulty"
    assert result.severity == SeverityLevel.CRITICAL
    assert result.ambulance_requirement == AmbulanceType.ALS


def test_extraction_code_mixed():
    """Code-mixed Hinglish and Marathish inputs."""
    provider = MockProvider()

    # Hinglish
    r_hinglish = provider.extract_emergency_info(
        "Bhai jaldi aao, Kurla signal pe bike slip ho gayi bohot blood nikal raha hai"
    )
    assert "Code-Mixed" in r_hinglish.detected_language
    assert r_hinglish.emergency_type == "Road Traffic Accident"
    assert r_hinglish.location == "Kurla Signal"

    # Marathish
    r_marathish = provider.extract_emergency_info(
        "Station baher accident zala ahe, severe head injury, please fast"
    )
    assert "Code-Mixed" in r_marathish.detected_language
    assert r_marathish.emergency_type == "Road Traffic Accident"


# ===========================================================================
# 2. Typos, Slang, and Panic Phrasing
# ===========================================================================

def test_extraction_typos_and_slang():
    """Input with heavy informal internet slang, abbreviations, and typos."""
    provider = MockProvider()
    result = provider.extract_emergency_info(
        "plzzzz hlp fast accidnt near rly stn some1 bleedin brdr hlp asap"
    )
    assert result.emergency_type == "Road Traffic Accident"
    assert any("bleeding" in s or "hemorrhage" in s for s in result.symptoms)
    assert result.confidence_score > 0.0


def test_extraction_panic_phrasing():
    """Panic-style caller phrasing with repetitive distress words and caps."""
    provider = MockProvider()
    result = provider.extract_emergency_info(
        "HELP HELP HELP MY FATHER COLLAPSED NOT BREATHING PLEASE HURRY PLEASE PLEASE!!!"
    )
    assert result.conscious_status == "unconscious"
    assert result.breathing_status == "stopped"
    assert result.severity == SeverityLevel.CRITICAL
    assert result.ambulance_requirement == AmbulanceType.ALS
    assert "panic" in result.clinical_rationale.lower()


# ===========================================================================
# 3. Missing Location and Contradictory Input Handling
# ===========================================================================

def test_extraction_missing_location(db_session):
    """
    When location is omitted, the AI must NOT fail:
    - Sets location to None
    - Flags missing location in missing_information
    - For high/critical severity, routes to HumanReview for callback
    """
    case = _create_test_case(
        db_session,
        "Someone fell down from terrace, head bleeding heavily, urgent help needed"
    )
    updated = process_case_extraction(case.id, db_session)

    assert updated.extracted_info.extracted_location_text is None
    assert "exact location / landmark" in updated.extracted_info.raw_llm_output["missing_information"]
    # Missing location on severe case must route to human review
    assert updated.status == CaseStatus.UNDER_REVIEW
    assert len(updated.human_reviews) >= 1
    assert "location" in updated.human_reviews[-1].trigger_reason.lower()


def test_extraction_contradictory_input():
    """Contradictory inputs must be flagged and lower confidence."""
    provider = MockProvider()
    result = provider.extract_emergency_info(
        "The patient is totally fine with no injury but dead on road and walking"
    )
    assert result.is_contradictory is True
    assert result.contradiction_notes is not None
    assert result.confidence_score < 0.65


# ===========================================================================
# 4. Fail-Safe Resilience: LLM Timeout and API Failure
# ===========================================================================

def test_llm_timeout_fail_safe(db_session):
    """
    CRITICAL REQUIREMENT:
    If the LLM times out:
    - DO NOT lose the case.
    - Mark extraction failure.
    - Route the case toward human review.
    """
    case = _create_test_case(db_session, "Car crash near Marine Drive")
    timeout_provider = MockProvider(simulate_timeout=True)

    updated = process_case_extraction(case.id, db_session, provider=timeout_provider)

    # 1. Case is intact and saved
    assert updated.id == case.id
    # 2. Case is routed to human review
    assert updated.status == CaseStatus.UNDER_REVIEW
    # 3. Priority escalated for safety
    assert updated.priority == SeverityLevel.HIGH
    # 4. Extraction record marks failure
    assert updated.extracted_info.emergency_type == "EXTRACTION_FAILED"
    assert updated.extracted_info.extraction_confidence == 0.0
    # 5. Human review entry created
    assert len(updated.human_reviews) >= 1
    assert "LLMTimeoutError" in updated.human_reviews[-1].trigger_reason
    # 6. Audit trail exists
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.action == "EXTRACTION_FAILED_ROUTED_TO_HUMAN_REVIEW")
        .first()
    )
    assert audit is not None


def test_llm_api_failure_fail_safe(db_session):
    """
    If the upstream LLM API returns 5xx error or network failure:
    - DO NOT lose the case.
    - Route to human review with escalated priority.
    """
    case = _create_test_case(db_session, "Fire in apartment building Bandra")
    api_fail_provider = MockProvider(simulate_api_error=True)

    updated = process_case_extraction(case.id, db_session, provider=api_fail_provider)

    assert updated.status == CaseStatus.UNDER_REVIEW
    assert updated.priority == SeverityLevel.HIGH
    assert updated.extracted_info.emergency_type == "EXTRACTION_FAILED"
    assert len(updated.human_reviews) >= 1
    assert "LLMAPIError" in updated.human_reviews[-1].trigger_reason


# ===========================================================================
# 5. Malformed JSON Recovery & Parsing
# ===========================================================================

def test_malformed_json_recovery():
    """Test multi-stage recovery for markdown fences, text wrappers, and trailing commas."""
    # 1. Wrapped in markdown code fence
    fence_json = """```json
    {
      "emergency_type": "Road Traffic Accident",
      "symptoms": ["bleeding"],
      "location": "Dadar",
      "severity": "HIGH",
      "patient_count": 1,
      "detected_language": "English",
      "ambulance_requirement": "ALS",
      "missing_information": [],
      "conscious_status": "conscious",
      "breathing_status": "normal",
      "clinical_rationale": "High severity trauma.",
      "confidence_score": 0.85
    }
    ```"""
    parsed1 = parse_and_validate_extraction(fence_json)
    assert parsed1.emergency_type == "Road Traffic Accident"
    assert parsed1.severity == SeverityLevel.HIGH

    # 2. Wrapped in conversational text with trailing commas
    dirty_json = """Here is the extracted clinical data for triage:
    {
      "emergency_type": "Cardiac Emergency",
      "symptoms": ["chest pain", "sweating",],
      "location": "Marine Drive",
      "severity": "CRITICAL",
      "patient_count": 1,
      "detected_language": "English",
      "ambulance_requirement": "ALS",
      "missing_information": [],
      "conscious_status": "unconscious",
      "breathing_status": "difficulty",
      "clinical_rationale": "Acute coronary syndrome symptoms with collapse.",
      "confidence_score": 0.90,
    }
    Please let me know if you need anything else!"""
    parsed2 = parse_and_validate_extraction(dirty_json)
    assert parsed2.emergency_type == "Cardiac Emergency"
    assert parsed2.severity == SeverityLevel.CRITICAL
    assert len(parsed2.symptoms) == 2


def test_unrecoverable_malformed_json_triggers_fail_safe(db_session):
    """When an LLM returns completely unrecoverable junk text, fail-safe preserves the case."""
    case = _create_test_case(db_session, "Elderly woman fell in bathroom")
    bad_json_provider = MockProvider(simulate_malformed_json=True)

    updated = process_case_extraction(case.id, db_session, provider=bad_json_provider)

    assert updated.status == CaseStatus.UNDER_REVIEW
    assert updated.priority == SeverityLevel.HIGH
    assert updated.extracted_info.emergency_type == "EXTRACTION_FAILED"
    assert len(updated.human_reviews) >= 1
    assert "LLMOutputFormatError" in updated.human_reviews[-1].trigger_reason


# ===========================================================================
# 6. Provider Independence Verification
# ===========================================================================

def test_provider_independence(db_session):
    """Verify that any custom LLMProvider class can be plugged in without changing business logic."""

    class CustomTestProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return "custom_vendor"

        def extract_emergency_info(self, raw_text: str, modality: str = "text", context=None):
            return EmergencyExtractionResult(
                emergency_type="Pediatric Emergency",
                symptoms=["high fever", "seizure"],
                location="Kothrud",
                severity=SeverityLevel.HIGH,
                patient_count=1,
                detected_language="English",
                ambulance_requirement=AmbulanceType.ALS,
                missing_information=[],
                conscious_status="semi-conscious",
                breathing_status="normal",
                clinical_rationale="Febrile seizure in pediatric patient requires urgent ALS response.",
                confidence_score=0.92,
            )

    case = _create_test_case(db_session, "My child is having a seizure at Kothrud")
    custom_provider = CustomTestProvider()
    updated = process_case_extraction(case.id, db_session, provider=custom_provider)

    assert updated.status == CaseStatus.TRIAGED
    assert updated.priority == SeverityLevel.HIGH
    assert updated.ai_decisions[-1].model_name == "custom_vendor"
    assert updated.extracted_info.emergency_type == "Pediatric Emergency"


# ===========================================================================
# 7. End-to-End REST API Integration (POST /api/v1/cases/{case_id}/triage)
# ===========================================================================

def test_triage_api_endpoint(client):
    """Test POST /api/v1/cases/{case_id}/triage endpoint via HTTP client."""
    # 1. Create a case
    created = client.post(
        "/api/v1/cases",
        json={"raw_input": "Cardiac arrest at Swargate bus stand, caller in tears"},
    ).json()
    case_id = created["id"]

    # 2. Trigger triage
    r = client.post(f"/api/v1/cases/{case_id}/triage")
    assert r.status_code == 200, r.json()
    data = r.json()

    assert data["id"] == case_id
    assert data["status"] in ("TRIAGED", "UNDER_REVIEW")
    assert data["emergency_type"] == "Cardiac Emergency"
    assert data["priority"] == "CRITICAL"
    assert data["recommended_ambulance"] == "ALS"
    assert data["extraction_status"] == "SUCCESS"
    assert data["confidence_score"] > 0.0


# ===========================================================================
# 8. Provider Abstraction Hierarchy Verification
# ===========================================================================

def test_provider_abstraction_hierarchy():
    """
    Verify strict provider abstraction hierarchy:
    LLMProvider
        ↓
    GrokProvider
        ↓
    MockProvider

    All AI business logic must communicate through LLMProvider.
    """
    assert issubclass(GrokProvider, LLMProvider)
    assert issubclass(MockProvider, GrokProvider)
    assert issubclass(MockProvider, LLMProvider)

    mock_inst = MockProvider()
    assert isinstance(mock_inst, LLMProvider)
    assert isinstance(mock_inst, GrokProvider)

    grok_inst = GrokProvider(api_key="test-api-key")
    assert isinstance(grok_inst, LLMProvider)
    assert grok_inst.provider_name == "grok"
    assert mock_inst.provider_name == "mock"


# ===========================================================================
# 9. Grok REST API Provider Mock Tests (No OpenAI SDK)
# ===========================================================================

def test_grok_provider_direct_rest_call():
    """Verify GrokProvider performs direct REST API HTTP POST without OpenAI SDK."""
    mock_response_payload = {
        "choices": [
            {
                "message": {
                    "content": """{
                        "emergency_type": "Road Traffic Accident",
                        "symptoms": ["head trauma", "arterial bleeding"],
                        "location": "Marine Drive",
                        "severity": "CRITICAL",
                        "patient_count": 2,
                        "detected_language": "English",
                        "ambulance_requirement": "ALS",
                        "missing_information": [],
                        "conscious_status": "unconscious",
                        "breathing_status": "difficulty",
                        "clinical_rationale": "High-speed collision with head trauma and arterial bleeding.",
                        "confidence_score": 0.95,
                        "is_contradictory": false,
                        "contradiction_notes": null
                    }"""
                }
            }
        ]
    }

    provider = GrokProvider(
        api_key="xai-test-key-12345",
        api_url="https://api.x.ai/v1/chat/completions",
        model="grok-beta",
    )

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_payload
        mock_post.return_value = mock_resp

        result = provider.extract_emergency_info(
            "Horrific car accident at Marine Drive, 2 people bleeding from head"
        )

        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer xai-test-key-12345"
        assert call_kwargs["json"]["model"] == "grok-beta"

        # Verify parsed Pydantic extraction
        assert isinstance(result, EmergencyExtractionResult)
        assert result.emergency_type == "Road Traffic Accident"
        assert result.severity == SeverityLevel.CRITICAL
        assert result.ambulance_requirement == AmbulanceType.ALS
        assert result.patient_count == 2
        assert result.location == "Marine Drive"
        assert result.confidence_score == 0.95


def test_grok_provider_retry_malformed_recovery():
    """Verify GrokProvider automatically retries and recovers when initial response is malformed."""
    bad_payload = {"choices": [{"message": {"content": "Sorry, I am thinking... not JSON!"}}]}
    good_payload = {
        "choices": [
            {
                "message": {
                    "content": """{
                        "emergency_type": "Cardiac Emergency",
                        "symptoms": ["chest pain"],
                        "location": "Dadar Station",
                        "severity": "HIGH",
                        "patient_count": 1,
                        "detected_language": "English",
                        "ambulance_requirement": "ALS",
                        "missing_information": [],
                        "conscious_status": "conscious",
                        "breathing_status": "normal",
                        "clinical_rationale": "Cardiac symptoms.",
                        "confidence_score": 0.88,
                        "is_contradictory": false
                    }"""
                }
            }
        ]
    }

    provider = GrokProvider(api_key="test-key", max_retries=2)

    with patch("httpx.Client.post") as mock_post:
        resp_bad = MagicMock()
        resp_bad.status_code = 200
        resp_bad.json.return_value = bad_payload

        resp_good = MagicMock()
        resp_good.status_code = 200
        resp_good.json.return_value = good_payload

        mock_post.side_effect = [resp_bad, resp_good]

        result = provider.extract_emergency_info("Chest pain at Dadar")
        assert result.emergency_type == "Cardiac Emergency"
        assert mock_post.call_count == 2


def test_grok_provider_timeout_exception():
    """Verify GrokProvider maps httpx.TimeoutException to LLMTimeoutError."""
    provider = GrokProvider(api_key="test-key", max_retries=0)

    with patch("httpx.Client.post") as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out")

        with pytest.raises(LLMTimeoutError):
            provider.extract_emergency_info("Cardiac arrest")


def test_grok_provider_http_500_api_error():
    """Verify GrokProvider maps non-200 HTTP responses to LLMAPIError."""
    provider = GrokProvider(api_key="test-key", max_retries=0)

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMAPIError):
            provider.extract_emergency_info("Emergency call")


def test_grok_provider_fail_safe_in_case_processing(db_session):
    """Verify process_case_extraction with GrokProvider failure NEVER loses the case."""
    case = _create_test_case(db_session, "Grok API failure simulation")
    provider = GrokProvider(api_key="test-key", max_retries=0)

    with patch.object(provider, "extract_emergency_info", side_effect=LLMAPIError("Grok service 503")):
        updated = process_case_extraction(case.id, db_session, provider=provider)

        assert updated.id == case.id
        assert updated.status == CaseStatus.UNDER_REVIEW
        assert updated.priority == SeverityLevel.HIGH
        assert updated.extracted_info.emergency_type == "EXTRACTION_FAILED"
        assert len(updated.human_reviews) >= 1
        assert "LLMAPIError" in updated.human_reviews[-1].trigger_reason


# ===========================================================================
# 10. Advanced Malformed JSON Recovery & Pydantic Coercion
# ===========================================================================

def test_json_recovery_python_literals_and_comments():
    """Recovery from trailing commas, comments, and Python None/True/False."""
    raw = """// AI Emergency Output
    {
      "emergency_type": "Trauma",
      "symptoms": ["leg laceration"],
      "location": None, /* caller did not specify */
      "severity": "MODERATE",
      "patient_count": 1,
      "detected_language": "English",
      "ambulance_requirement": "BLS",
      "missing_information": ["location"],
      "is_contradictory": False,
      "clinical_rationale": "Laceration with stable vitals.",
      "confidence_score": 0.80,
    }"""
    result = parse_and_validate_extraction(raw)
    assert result.emergency_type == "Trauma"
    assert result.location is None
    assert result.is_contradictory is False
    assert result.severity == SeverityLevel.MODERATE


def test_json_recovery_python_dict_ast():
    """Recovery from raw Python dictionary representation via AST fallback."""
    raw = """{'emergency_type': 'Burn Injury', 'symptoms': ['second degree burns'], 'location': 'Kurla', 'severity': 'HIGH', 'patient_count': 1, 'detected_language': 'English', 'ambulance_requirement': 'ALS', 'clinical_rationale': 'Extensive burns', 'confidence_score': 0.89}"""
    result = parse_and_validate_extraction(raw)
    assert result.emergency_type == "Burn Injury"
    assert result.location == "Kurla"
    assert result.severity == SeverityLevel.HIGH


def test_pydantic_key_normalization_and_coercion():
    """Verify normalization of alternate keys ('ambulance', 'missing_info') and string patient count."""
    data = {
        "emergency_type": "General Medical Emergency",
        "symptoms": ["dizziness"],
        "ambulance": "BLS",
        "missing_info": ["address"],
        "language": "Hindi",
        "patient_count": "3 people",
        "confidence": 0.82,
    }
    obj = EmergencyExtractionResult.model_validate(data)
    assert obj.ambulance_requirement == AmbulanceType.BLS
    assert obj.missing_information == ["address"]
    assert obj.detected_language == "Hindi"
    assert obj.patient_count == 3
    assert obj.confidence_score == 0.82


"""
Tests for the Emergency Input Module (Module 1 — Synopsis).

Covers:
- Standard English
- Hindi (Devanagari)
- Marathi (Devanagari)
- Code-mixed language (Hinglish, Marathish)
- Typos and slang
- Panic-style messages
- Incomplete descriptions (NOT rejected)
- Voice/Audio modality readiness
- Initial case status (PENDING), timestamp, modality, raw input persistence
- AuditLog entry creation (stage=INTAKE)
- Retrieval by ID and 404 handling
- Invalid inputs: empty text, whitespace only, missing audio for voice, unsupported modality, empty body
"""
import uuid
import pytest
from app.db.session import SessionLocal
from app.models.case import Case, CaseStatus, InputModality
from app.models.audit import AuditLog, AuditStage

CASES_URL = "/api/v1/cases"


# ===========================================================================
# 1. Multi-lingual, Noisy, Panic, and Incomplete Input Tests (Valid Cases)
# ===========================================================================

def test_create_case_english_standard(client):
    """Standard English description with location and symptoms."""
    payload = {
        "raw_input": "Severe two-car collision at Marine Drive near Nariman Point. Two people unconscious and bleeding.",
        "caller_phone": "+919876543210",
    }
    r = client.post(CASES_URL, json=payload)
    assert r.status_code == 201, r.json()
    data = r.json()

    assert data["id"]
    assert data["raw_input"] == payload["raw_input"]
    assert data["raw_text"] == payload["raw_input"]
    assert data["modality"] == "text"
    assert data["status"] == "PENDING"
    assert data["caller_phone"] == "+919876543210"
    assert data["created_at"]
    assert data["updated_at"]


def test_create_case_hindi_devanagari(client):
    """Hindi input in Devanagari script must be ingested and preserved without encoding issues."""
    hindi_text = "यहाँ अंधेरी स्टेशन के पास एक्सीडेंट हुआ है बहुत खून बह रहा है जल्दी एम्बुलेंस भेजो"
    payload = {
        "raw_text": hindi_text,
        "caller_phone": "+919123456789",
    }
    r = client.post(CASES_URL, json=payload)
    assert r.status_code == 201, r.json()
    data = r.json()

    assert data["raw_text"] == hindi_text
    assert data["raw_input"] == hindi_text
    assert data["status"] == "PENDING"
    assert data["modality"] == "text"


def test_create_case_marathi_devanagari(client):
    """Marathi input in Devanagari script must be stored and accepted."""
    marathi_text = "दादर स्टेशन जवळ एक व्यक्ती बेशुद्ध पडली आहे, श्वास घ्यायला प्रचंड त्रास होतोय"
    payload = {
        "raw_input": marathi_text,
    }
    r = client.post(CASES_URL, json=payload)
    assert r.status_code == 201, r.json()
    data = r.json()

    assert data["raw_input"] == marathi_text
    assert data["status"] == "PENDING"


def test_create_case_code_mixed_hinglish(client):
    """Code-mixed Hinglish (Hindi + English romanized)."""
    hinglish_text = "Bhai jaldi aao, Kurla signal pe bike slip ho gayi bohot blood nikal raha hai please send ambulance"
    r = client.post(CASES_URL, json={"raw_input": hinglish_text})
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["raw_input"] == hinglish_text
    assert data["status"] == "PENDING"


def test_create_case_code_mixed_marathish(client):
    """Code-mixed Marathi + English romanized."""
    marathish_text = "Station baher accident zala ahe, severe head injury, please fast"
    r = client.post(CASES_URL, json={"raw_input": marathish_text})
    assert r.status_code == 201, r.json()
    assert r.json()["raw_input"] == marathish_text


def test_create_case_typos_and_slang(client):
    """Input with heavy typos, abbreviations, and informal internet slang."""
    typo_text = "plzzzz hlp fast accidnt near rly stn some1 bleedin brdr hlp asap"
    r = client.post(CASES_URL, json={"raw_input": typo_text})
    assert r.status_code == 201, r.json()
    assert r.json()["raw_input"] == typo_text
    assert r.json()["status"] == "PENDING"


def test_create_case_panic_style_messages(client):
    """Panic-style caller message in all caps, repetitive, punctuation heavy."""
    panic_text = "HELP HELP HELP MY FATHER COLLAPSED NOT BREATHING PLEASE HURRY PLEASE PLEASE!!!"
    r = client.post(CASES_URL, json={"raw_input": panic_text})
    assert r.status_code == 201, r.json()
    assert r.json()["raw_input"] == panic_text
    assert r.json()["status"] == "PENDING"


@pytest.mark.parametrize(
    "incomplete_text",
    [
        "someone fell down",
        "accident",
        "unconscious man on road",
        "chest pain help",
        "bleeding",
    ],
)
def test_create_case_incomplete_descriptions_not_rejected(client, incomplete_text):
    """
    CRITICAL REQUIREMENT:
    Do NOT reject a genuine emergency simply because information is incomplete.
    Missing information is identified later by the AI extraction system.
    """
    r = client.post(CASES_URL, json={"raw_input": incomplete_text})
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["raw_input"] == incomplete_text
    assert data["status"] == "PENDING"


# ===========================================================================
# 2. Voice / Audio Modality Readiness Tests
# ===========================================================================

def test_create_case_voice_modality_with_audio_url(client):
    """System must be architecturally ready for voice/audio streams."""
    audio_payload = {
        "modality": "voice",
        "audio_url": "https://storage.sahayai.org/recordings/call_2026_09_25_001.wav",
        "caller_phone": "+919876500000",
    }
    r = client.post(CASES_URL, json=audio_payload)
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["modality"] == "voice"
    assert data["audio_url"] == audio_payload["audio_url"]
    assert data["status"] == "PENDING"
    assert "[Audio stream/recording received" in data["raw_input"]


def test_create_case_voice_modality_with_transcript_and_url(client):
    """Voice emergency with both live transcript and underlying audio URL."""
    voice_payload = {
        "modality": "voice",
        "raw_input": "Caller says chest pain at Swargate bus stand",
        "audio_url": "https://storage.sahayai.org/audio/live_transcription_12.ogg",
        "caller_phone": "+919822001122",
    }
    r = client.post(CASES_URL, json=voice_payload)
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["modality"] == "voice"
    assert data["raw_input"] == voice_payload["raw_input"]
    assert data["audio_url"] == voice_payload["audio_url"]


# ===========================================================================
# 3. Persistence and Audit Trail Verification
# ===========================================================================

def test_case_persistence_and_audit_log_creation(client):
    """Verify that case and its initial INTAKE audit log are persisted in the database."""
    r = client.post(
        CASES_URL,
        json={"raw_input": "Cardiac arrest at Kothrud depot", "caller_phone": "+919811122233"},
    )
    assert r.status_code == 201, r.json()
    case_id = r.json()["id"]

    # Verify directly via SQLAlchemy DB session
    with SessionLocal() as db:
        case = db.query(Case).filter(Case.id == case_id).first()
        assert case is not None
        assert case.raw_text == "Cardiac arrest at Kothrud depot"
        assert case.status == CaseStatus.PENDING
        assert case.modality == "text"
        assert case.created_at is not None

        # Verify audit log entry
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.case_id == case_id, AuditLog.stage == AuditStage.INTAKE)
            .first()
        )
        assert audit is not None
        assert audit.action == "EMERGENCY_INTAKE_RECEIVED"
        assert audit.actor == "CITIZEN_PORTAL"
        assert audit.details["modality"] == "text"


def test_get_case_by_id(client):
    """Retrieve an existing case by its UUID."""
    created = client.post(CASES_URL, json={"raw_input": "Traffic accident on Western Express Highway"}).json()
    case_id = created["id"]

    r = client.get(f"{CASES_URL}/{case_id}")
    assert r.status_code == 200, r.json()
    retrieved = r.json()
    assert retrieved["id"] == case_id
    assert retrieved["raw_input"] == "Traffic accident on Western Express Highway"
    assert retrieved["status"] == "PENDING"


def test_get_nonexistent_case_returns_404(client):
    """Querying a non-existent UUID returns clean 404 JSON."""
    fake_id = str(uuid.uuid4())
    r = client.get(f"{CASES_URL}/{fake_id}")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not_found"


# ===========================================================================
# 4. Invalid Input Rejection Tests
# ===========================================================================

def test_invalid_empty_string_rejected(client):
    """An empty raw_input string must be rejected with 422 Unprocessable Entity."""
    r = client.post(CASES_URL, json={"raw_input": ""})
    assert r.status_code == 422


def test_invalid_whitespace_only_rejected(client):
    """Pure whitespace (spaces, tabs, newlines) must be rejected with 422."""
    r = client.post(CASES_URL, json={"raw_input": "   \n\t  \r  "})
    assert r.status_code == 422


def test_invalid_empty_body_rejected(client):
    """Empty JSON object must be rejected with 422."""
    r = client.post(CASES_URL, json={})
    assert r.status_code == 422


def test_invalid_unsupported_modality_rejected(client):
    """Modality outside ('text', 'voice', 'audio') must be rejected with 422."""
    r = client.post(CASES_URL, json={"raw_input": "Emergency", "modality": "telepathy"})
    assert r.status_code == 422


def test_invalid_voice_without_audio_or_text_rejected(client):
    """Voice modality without either text transcript or audio URL must be rejected with 422."""
    r = client.post(CASES_URL, json={"modality": "voice"})
    assert r.status_code == 422

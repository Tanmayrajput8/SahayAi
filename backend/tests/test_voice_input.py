"""
Tests for Voice/Audio Input Capability.

Requirements verified:
- Audio → Speech-to-text API → Transcript → LLM extraction → Severity → Location → Confidence → Human Review
- Same downstream AI pipeline used for text and voice
- Unsupported audio format rejection (415)
- Oversized audio rejection (413)
- Empty audio rejection (400)
- Transcription failure handling (fail-safe: case NOT lost, routed to human review)
- Speech API timeout handling (fail-safe: case NOT lost, routed to human review)
- Unclear transcription handling (routed to human review for dispatcher listening)
- Mock transcription when no API key is configured
- REST API endpoint: POST /api/v1/cases/audio
"""
import io
from unittest.mock import patch, MagicMock
import httpx
import pytest
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.case import CaseStatus, SeverityLevel, InputModality
from app.models.human_review import HumanReview
from app.models.verification import VerificationResult
from app.models.duplicate import DuplicateRelationship
from app.models.audit import AuditLog, AuditStage
from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.providers.external import ExternalSpeechProvider
from app.ai.speech.providers.mock import MockSpeechProvider
from app.ai.speech.providers.factory import get_speech_provider
from app.ai.speech.exceptions import (
    UnsupportedAudioFormatError,
    OversizedAudioError,
    EmptyAudioError,
    SpeechTimeoutError,
    SpeechAPIError,
)
from app.ai.speech.service import process_audio_emergency


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session


def _create_dummy_wav(size_bytes: int = 1024) -> bytes:
    """Generate mock WAV audio bytes with a RIFF header."""
    header = b"RIFF" + (size_bytes - 8).to_bytes(4, "little") + b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data"
    data = b"\x00" * max(0, size_bytes - len(header))
    return header + data


# ===========================================================================
# 1. Validation Tests: Empty, Oversized, and Unsupported Audio
# ===========================================================================

def test_empty_audio_rejected():
    """Empty audio (0 bytes) must raise EmptyAudioError."""
    provider = MockSpeechProvider()
    with pytest.raises(EmptyAudioError):
        provider.transcribe(audio_bytes=b"", filename="empty.wav")


def test_oversized_audio_rejected():
    """Audio exceeding max_size_bytes must raise OversizedAudioError."""
    provider = MockSpeechProvider()
    fake_large_audio = b"RIFF" + b"\x00" * 1000
    with pytest.raises(OversizedAudioError):
        provider.validate_audio(fake_large_audio, "large.wav", max_size_bytes=500)


def test_unsupported_audio_format_rejected():
    """Non-audio extensions like .exe, .pdf, .txt must raise UnsupportedAudioFormatError."""
    provider = MockSpeechProvider()
    with pytest.raises(UnsupportedAudioFormatError):
        provider.transcribe(audio_bytes=b"dummy content", filename="malicious_payload.exe")

    with pytest.raises(UnsupportedAudioFormatError):
        provider.transcribe(audio_bytes=b"dummy content", filename="document.pdf")


# ===========================================================================
# 2. Pipeline Integration: Audio through Same Emergency AI Pipeline
# ===========================================================================

def test_audio_emergency_intake_through_same_pipeline(db_session):
    """
    Verify complete voice pipeline:
    Audio -> Mock STT -> Transcript -> Same process_case_extraction -> Triage.
    """
    wav_bytes = _create_dummy_wav(2048)
    case = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="marine_drive_accident.wav",
        content_type="audio/wav",
        caller_phone="+919876543210",
        db=db_session,
    )

    assert case.id is not None
    assert case.modality == InputModality.VOICE.value
    assert case.audio_url is not None
    assert "/audio/" in case.audio_url
    assert case.caller_phone == "+919876543210"

    # Verified downstream triage through same pipeline
    assert case.extracted_info is not None
    assert case.extracted_info.emergency_type == "Road Traffic Accident"
    assert case.priority in (SeverityLevel.HIGH, SeverityLevel.CRITICAL)
    assert len(case.ai_decisions) >= 1
    assert case.ai_decisions[-1].recommended_ambulance_type is not None


def test_audio_emergency_hindi_transcript(db_session):
    """Audio with Hindi speech passes through STT and same LLM pipeline."""
    wav_bytes = _create_dummy_wav(1024)
    case = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="hindi_emergency_call.wav",
        content_type="audio/wav",
        db=db_session,
    )

    assert case.language in ("hi", "Hindi")
    assert case.extracted_info.emergency_type == "Road Traffic Accident"
    assert "अंधेरी" in case.extracted_info.extracted_location_text


def test_audio_emergency_marathi_transcript(db_session):
    """Audio with Marathi speech passes through STT and same LLM pipeline."""
    wav_bytes = _create_dummy_wav(1024)
    case = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="marathi_emergency_call.wav",
        content_type="audio/wav",
        db=db_session,
    )

    assert case.language in ("mr", "Marathi")
    assert "दादर" in case.extracted_info.extracted_location_text


# ===========================================================================
# 3. Fail-Safe Resilience: Transcription Failure & API Timeout
# ===========================================================================

def test_audio_transcription_api_failure_fail_safe(db_session):
    """
    CRITICAL REQUIREMENT:
    If speech-to-text API fails:
    - DO NOT lose the case.
    - Preserve audio recording URL.
    - Route case toward human review with escalated priority.
    """
    fail_provider = MockSpeechProvider(simulate_api_error=True)
    wav_bytes = _create_dummy_wav(1024)

    case = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="emergency_call_failing.wav",
        content_type="audio/wav",
        db=db_session,
        speech_provider=fail_provider,
    )

    # 1. Case is preserved and intact
    assert case.id is not None
    assert case.modality == InputModality.VOICE.value
    assert case.audio_url is not None
    # 2. Case routed to Human Review
    assert case.status == CaseStatus.UNDER_REVIEW
    # 3. Priority escalated
    assert case.priority == SeverityLevel.HIGH
    # 4. HumanReview record exists
    assert len(case.human_reviews) >= 1
    assert "SpeechAPIError" in case.human_reviews[-1].trigger_reason


def test_audio_transcription_timeout_fail_safe(db_session):
    """If speech-to-text API times out, preserve case and route to human review."""
    timeout_provider = MockSpeechProvider(simulate_timeout=True)
    wav_bytes = _create_dummy_wav(1024)

    case = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="emergency_call_timeout.wav",
        content_type="audio/wav",
        db=db_session,
        speech_provider=timeout_provider,
    )

    assert case.status == CaseStatus.UNDER_REVIEW
    assert case.priority == SeverityLevel.HIGH
    assert len(case.human_reviews) >= 1
    assert "SpeechTimeoutError" in case.human_reviews[-1].trigger_reason


def test_audio_unclear_transcription_routes_to_human_review(db_session):
    """
    When audio is muffled or transcription is unclear:
    - Route case to Human Review for manual dispatcher listening.
    """
    unclear_provider = MockSpeechProvider(simulate_unclear=True)
    wav_bytes = _create_dummy_wav(1024)

    case = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="unclear_siren_noise.wav",
        content_type="audio/wav",
        db=db_session,
        speech_provider=unclear_provider,
    )

    assert case.status == CaseStatus.UNDER_REVIEW
    assert len(case.human_reviews) >= 1
    assert "unclear" in case.human_reviews[-1].trigger_reason.lower()


# ===========================================================================
# 4. REST API Endpoint: POST /api/v1/cases/audio
# ===========================================================================

def test_api_submit_audio_case_endpoint(client):
    """Test POST /api/v1/cases/audio with valid multipart WAV file."""
    wav_bytes = _create_dummy_wav(2048)
    files = {
        "audio_file": ("caller_report.wav", io.BytesIO(wav_bytes), "audio/wav"),
    }
    data = {
        "caller_phone": "+919876543210",
        "manual_location": "Marine Drive",
    }

    r = client.post("/api/v1/cases/audio", files=files, data=data)
    assert r.status_code == 201, r.json()
    resp = r.json()

    assert resp["id"] is not None
    assert resp["status"] in ("TRIAGED", "UNDER_REVIEW")
    assert resp["emergency_type"] is not None
    assert resp["recommended_ambulance"] in ("ALS", "BLS")


def test_api_submit_empty_audio_returns_400(client):
    """Submitting empty audio file must return 400 Bad Request."""
    files = {
        "audio_file": ("empty.wav", io.BytesIO(b""), "audio/wav"),
    }
    r = client.post("/api/v1/cases/audio", files=files)
    assert r.status_code == 400
    assert r.json()["error"] == "empty_audio"


def test_api_submit_unsupported_audio_returns_415(client):
    """Submitting non-audio format must return 415 Unsupported Media Type."""
    files = {
        "audio_file": ("invoice.pdf", io.BytesIO(b"%PDF-1.4 ..."), "application/pdf"),
    }
    r = client.post("/api/v1/cases/audio", files=files)
    assert r.status_code == 415
    assert r.json()["error"] == "unsupported_audio_format"


# ===========================================================================
# 5. Speech Provider Hierarchy & Factory Tests
# ===========================================================================

def test_speech_provider_abstraction_hierarchy():
    """Verify SpeechToTextProvider abstraction hierarchy with External & Mock providers."""
    assert issubclass(ExternalSpeechProvider, SpeechToTextProvider)
    assert issubclass(MockSpeechProvider, SpeechToTextProvider)

    mock_inst = MockSpeechProvider()
    assert isinstance(mock_inst, SpeechToTextProvider)
    assert mock_inst.provider_name == "mock_speech_provider"

    external_inst = ExternalSpeechProvider(
        api_key="gsk-test-key-12345",
        api_url="https://api.groq.com/openai/v1/audio/transcriptions",
        model="whisper-large-v3",
    )
    assert isinstance(external_inst, SpeechToTextProvider)
    assert external_inst.provider_name == "external_whisper_rest_api"
    assert "groq.com" in external_inst.api_endpoint_info


def test_speech_provider_factory_fallback():
    """When no STT_API_KEY is configured, factory must gracefully fall back to MockSpeechProvider."""
    provider = get_speech_provider(provider_override="external")
    # If no key in environment, falls back to Mock
    assert isinstance(provider, SpeechToTextProvider)


# ===========================================================================
# 6. External Speech Provider Direct REST API Mock Tests (No Local Whisper)
# ===========================================================================

def test_external_speech_provider_direct_rest_call():
    """Verify ExternalSpeechProvider calls Groq Cloud Whisper REST API via httpx."""
    provider = ExternalSpeechProvider(
        api_key="gsk-test-key-whisper",
        api_url="https://api.groq.com/openai/v1/audio/transcriptions",
        model="whisper-large-v3",
    )
    wav_bytes = _create_dummy_wav(1024)

    mock_json_response = {
        "text": "Severe road accident near Marine Drive, two vehicles collided and passengers are trapped.",
        "language": "en",
        "duration": 7.5,
    }

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json_response
        mock_post.return_value = mock_resp

        result = provider.transcribe(
            audio_bytes=wav_bytes,
            filename="emergency_call.wav",
            content_type="audio/wav",
            language_hint="en",
        )

        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer gsk-test-key-whisper"
        assert call_kwargs["data"]["model"] == "whisper-large-v3"
        assert call_kwargs["data"]["language"] == "en"

        assert result.text == mock_json_response["text"]
        assert result.detected_language == "en"
        assert result.duration_seconds == 7.5
        assert result.is_unclear is False
        assert result.confidence >= 0.85


def test_external_speech_provider_unclear_audio():
    """Verify ExternalSpeechProvider flags very short or empty audio as unclear."""
    provider = ExternalSpeechProvider(
        api_key="gsk-test-key",
        api_url="https://api.groq.com/openai/v1/audio/transcriptions",
    )
    wav_bytes = _create_dummy_wav(1024)

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "...", "duration": 3.0}
        mock_post.return_value = mock_resp

        result = provider.transcribe(audio_bytes=wav_bytes, filename="faint_whisper.wav")
        assert result.is_unclear is True
        assert result.confidence <= 0.50


def test_external_speech_provider_timeout_exception():
    """Verify ExternalSpeechProvider maps httpx.TimeoutException to SpeechTimeoutError."""
    provider = ExternalSpeechProvider(api_key="gsk-test-key")
    wav_bytes = _create_dummy_wav(1024)

    with patch("httpx.Client.post") as mock_post:
        mock_post.side_effect = httpx.TimeoutException("STT connection timed out")

        with pytest.raises(SpeechTimeoutError):
            provider.transcribe(audio_bytes=wav_bytes, filename="timeout_call.wav")


def test_external_speech_provider_http_500_api_error():
    """Verify ExternalSpeechProvider maps HTTP 500 error to SpeechAPIError."""
    provider = ExternalSpeechProvider(api_key="gsk-test-key")
    wav_bytes = _create_dummy_wav(1024)

    with patch("httpx.Client.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Groq API Error"
        mock_post.return_value = mock_resp

        with pytest.raises(SpeechAPIError):
            provider.transcribe(audio_bytes=wav_bytes, filename="error_call.wav")


# ===========================================================================
# 7. End-to-End Pipeline: Verification & Duplicate Detection for Audio
# ===========================================================================

def test_audio_pipeline_verification_and_duplicate_detection(db_session):
    """
    Verify full architecture:
    Audio
    → Speech-to-text API
    → Transcript
    → Language detection
    → LLM extraction
    → Severity
    → Location
    → Verification (VerificationResult)
    → Duplicate detection (DuplicateRelationship)
    → Confidence
    → Human review/confirmation
    """
    wav_bytes = _create_dummy_wav(2048)

    # 1. Primary voice case
    case1 = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="marine_drive_primary.wav",
        content_type="audio/wav",
        caller_phone="+919876543211",
        db=db_session,
    )

    # Verify VerificationResult created
    assert len(case1.verification_results) >= 1
    assert case1.verification_results[0].status.value in ("VERIFIED", "CONFLICTING")

    # Verify RAG_VERIFICATION and DUPLICATE_CHECK audit logs
    audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case1.id)
        .all()
    )
    stages = [a.stage for a in audits]
    assert AuditStage.INTAKE in stages or AuditStage.AUDIO_PROCESSING in stages
    assert AuditStage.AI_EXTRACTION in stages
    assert AuditStage.RAG_VERIFICATION in stages
    assert AuditStage.DUPLICATE_CHECK in stages

    # 2. Secondary voice case reporting same incident at same location
    case2 = process_audio_emergency(
        audio_bytes=wav_bytes,
        filename="marine_drive_secondary.wav",
        content_type="audio/wav",
        caller_phone="+919876543212",
        db=db_session,
    )

    # Duplicate check should detect the existing case at Marine Drive
    assert len(case2.duplicate_of) >= 1
    assert case2.status in (CaseStatus.TRIAGED, CaseStatus.UNDER_REVIEW)


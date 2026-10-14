"""Service for handling audio emergency intake and routing to the text LLM pipeline."""
import os
import uuid
import logging
from typing import Optional
from pathlib import Path
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.case import Case, CaseStatus, SeverityLevel, InputModality
from app.models.human_review import HumanReview, ReviewStatus
from app.models.audit import AuditLog, AuditStage
from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.providers.factory import get_speech_provider
from app.ai.speech.schemas import TranscriptionResult
from app.ai.service import process_case_extraction
from app.ai.providers.base import LLMProvider

logger = logging.getLogger(__name__)


def _save_audio_file(audio_bytes: bytes, filename: str) -> str:
    """Save audio bytes locally and return the storage URL/path."""
    upload_dir = settings.AUDIO_UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex[:12]}_{Path(filename).name}"
    filepath = os.path.join(upload_dir, safe_name)

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    return f"/audio/{safe_name}"


def process_audio_emergency(
    audio_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    caller_phone: Optional[str] = None,
    manual_location: Optional[str] = None,
    language_hint: Optional[str] = None,
    db: Session = None,  # type: ignore[assignment]
    speech_provider: Optional[SpeechToTextProvider] = None,
    llm_provider: Optional[LLMProvider] = None,
) -> Case:
    """
    Ingest audio emergency, transcribe using SpeechToTextProvider,
    and route the resulting transcript through the SAME emergency-understanding pipeline.

    Flow:
    Audio -> STT API -> Transcript -> Language Detection -> LLM Extraction
    -> Severity -> Location -> Confidence -> Human Review / Confirmation.
    """
    if speech_provider is None:
        speech_provider = get_speech_provider()

    # 1. Validation (Raises EmptyAudioError, OversizedAudioError, UnsupportedAudioFormatError)
    speech_provider.validate_audio(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=content_type,
        max_size_bytes=settings.MAX_AUDIO_SIZE_BYTES,
    )

    # 2. Persist audio recording for dispatcher access
    audio_url = _save_audio_file(audio_bytes, filename)

    # 3. Transcribe audio to text
    transcription_result: Optional[TranscriptionResult] = None
    transcription_error: Optional[Exception] = None

    try:
        transcription_result = speech_provider.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            language_hint=language_hint,
        )
    except Exception as exc:
        logger.error("Audio transcription failed: %s", exc, exc_info=True)
        transcription_error = exc

    # 4. Handle Transcription Failure (Fail-Safe: DO NOT LOSE THE CASE)
    if transcription_error is not None or transcription_result is None:
        case = Case(
            raw_text="[Audio emergency uploaded: transcription failed - dispatcher manual listen required]",
            modality=InputModality.VOICE.value,
            audio_url=audio_url,
            caller_phone=caller_phone,
            language="unknown",
            status=CaseStatus.UNDER_REVIEW,
            priority=SeverityLevel.HIGH,
        )
        db.add(case)
        db.flush()

        review = HumanReview(
            case_id=case.id,
            review_status=ReviewStatus.PENDING,
            trigger_reason=f"Audio Transcription Failure ({type(transcription_error).__name__}): {transcription_error}",
            original_decision={"audio_url": audio_url, "status": "TRANSCRIPTION_FAILED"},
        )
        db.add(review)

        audit = AuditLog(
            case_id=case.id,
            stage=AuditStage.INTAKE,
            actor=f"SPEECH_{speech_provider.provider_name.upper()}",
            action="AUDIO_TRANSCRIPTION_FAILED_ROUTED_TO_HUMAN_REVIEW",
            details={"error": str(transcription_error), "audio_url": audio_url},
        )
        db.add(audit)
        db.commit()
        db.refresh(case)
        return case

    assert transcription_result is not None
    # 5. Case creation with valid transcript
    transcript_text = transcription_result.text
    case = Case(
        raw_text=transcript_text,
        modality=InputModality.VOICE.value,
        audio_url=audio_url,
        caller_phone=caller_phone,
        language=transcription_result.detected_language or "unknown",
        status=CaseStatus.PENDING,
        priority=SeverityLevel.MODERATE,
    )
    db.add(case)
    db.flush()

    # Log initial intake audit
    audit_intake = AuditLog(
        case_id=case.id,
        stage=AuditStage.INTAKE,
        actor=f"SPEECH_{speech_provider.provider_name.upper()}",
        action="VOICE_INTAKE_TRANSCRIBED",
        details={
            "audio_url": audio_url,
            "duration_seconds": transcription_result.duration_seconds,
            "stt_confidence": transcription_result.confidence,
            "is_unclear": transcription_result.is_unclear,
        },
    )
    db.add(audit_intake)
    db.commit()

    # 6. Pass through the SAME emergency-understanding pipeline used for text
    updated_case = process_case_extraction(
        case_id=case.id,
        db=db,
        provider=llm_provider,
    )

    # 7. Unclear transcription handling: Ensure routed to Human Review
    if transcription_result.is_unclear:
        updated_case.status = CaseStatus.UNDER_REVIEW
        review = HumanReview(
            case_id=updated_case.id,
            review_status=ReviewStatus.PENDING,
            trigger_reason=(
                f"Unclear audio transcription (STT confidence: {transcription_result.confidence:.2f}). "
                "Manual dispatcher listening required."
            ),
            original_decision={
                "audio_url": audio_url,
                "transcript": transcript_text,
                "stt_confidence": transcription_result.confidence,
            },
        )
        db.add(review)
        db.commit()
        db.refresh(updated_case)

    return updated_case

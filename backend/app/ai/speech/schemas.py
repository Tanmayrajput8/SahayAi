"""Schemas for speech-to-text outputs."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class TranscriptionResult(BaseModel):
    """Normalized result returned by any SpeechToTextProvider."""
    text: str = Field(..., description="Transcribed text from speech audio")
    detected_language: Optional[str] = Field(
        default=None,
        description="Detected audio spoken language (e.g. 'en', 'hi', 'mr', 'unknown')",
    )
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Duration of audio recording in seconds if available",
    )
    confidence: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Transcription confidence score",
    )
    is_unclear: bool = Field(
        default=False,
        description="Flagged true if audio is muffled, heavily noisy, or unintelligible",
    )
    raw_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw provider response or acoustic diagnostics",
    )

    model_config = ConfigDict(extra="ignore")

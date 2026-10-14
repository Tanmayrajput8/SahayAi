"""Abstract Base Class for Speech-to-Text providers."""
from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path

from app.ai.speech.schemas import TranscriptionResult
from app.ai.speech.exceptions import (
    UnsupportedAudioFormatError,
    OversizedAudioError,
    EmptyAudioError,
)

# Supported audio extensions and MIME types
SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".webm", ".opus"
}
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/mp4",
    "audio/x-m4a", "audio/ogg", "audio/flac", "audio/x-flac", "audio/aac",
    "audio/webm", "video/webm", "application/octet-stream"
}


class SpeechToTextProvider(ABC):
    """Abstract Base Class for Speech-to-Text transcription."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the speech provider."""
        pass

    def validate_audio(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        max_size_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        """Validate audio size and format before dispatching to transcription."""
        # Check empty audio
        if not audio_bytes or len(audio_bytes) == 0:
            raise EmptyAudioError("Audio file is empty (0 bytes).")

        # Check oversized audio
        if len(audio_bytes) > max_size_bytes:
            raise OversizedAudioError(
                f"Audio file size ({len(audio_bytes)} bytes) exceeds maximum allowable limit of {max_size_bytes} bytes."
            )

        # Check file extension
        ext = Path(filename).suffix.lower()
        if ext and ext not in SUPPORTED_AUDIO_EXTENSIONS:
            raise UnsupportedAudioFormatError(
                f"Unsupported audio extension '{ext}'. Supported formats: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
            )

        # Check content-type if provided
        if content_type and content_type.lower() not in SUPPORTED_AUDIO_MIME_TYPES:
            # If extension is valid we allow it, otherwise reject
            if not ext or ext not in SUPPORTED_AUDIO_EXTENSIONS:
                raise UnsupportedAudioFormatError(
                    f"Unsupported audio MIME type '{content_type}'."
                )

    @abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio bytes to text transcript."""
        pass

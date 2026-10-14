"""External Speech-to-Text Provider using Cloud REST API (Groq Whisper Large v3 / OpenAI-compatible STT)."""
import logging
from typing import Optional
import httpx

from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.schemas import TranscriptionResult
from app.ai.speech.exceptions import (
    SpeechTimeoutError,
    SpeechAPIError,
)

logger = logging.getLogger(__name__)


class ExternalSpeechProvider(SpeechToTextProvider):
    """
    Cloud REST API Speech-to-Text provider.
    Uses Groq Whisper Cloud REST API (model: whisper-large-v3) or an OpenAI-compatible
    Whisper REST endpoint via httpx without downloading any local models.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.groq.com/openai/v1/audio/transcriptions",
        model: str = "whisper-large-v3",
        timeout: float = 20.0,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "external_whisper_rest_api"

    @property
    def api_endpoint_info(self) -> str:
        """Information on the exact external STT API configured."""
        return f"External Cloud REST STT: {self.api_url} (model: {self.model})"

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Validate audio and call the external speech-to-text REST API.
        Does not use local Whisper. Handles timeouts and API errors gracefully.
        """
        self.validate_audio(audio_bytes, filename, content_type)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        form_data = {
            "model": self.model,
            "response_format": "verbose_json",
        }
        if language_hint:
            form_data["language"] = language_hint

        mime = content_type or "audio/wav"
        files = {
            "file": (filename, audio_bytes, mime),
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.api_url,
                    headers=headers,
                    data=form_data,
                    files=files,
                )
        except httpx.TimeoutException as exc:
            raise SpeechTimeoutError(
                f"External Speech API timed out after {self.timeout}s: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise SpeechAPIError(
                f"Network error calling External Speech API: {exc}"
            ) from exc

        if response.status_code != 200:
            raise SpeechAPIError(
                f"External Speech API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            transcript_text = data.get("text", "").strip()
            detected_lang = data.get("language")
            duration = data.get("duration")

            # Check if transcription is unclear or empty
            is_unclear = not transcript_text or len(transcript_text) < 4
            confidence = 0.90 if not is_unclear else 0.30

            return TranscriptionResult(
                text=transcript_text or "[Inaudible / Unclear audio]",
                detected_language=detected_lang,
                duration_seconds=duration,
                confidence=confidence,
                is_unclear=is_unclear,
                raw_metadata=data,
            )
        except Exception as exc:
            raise SpeechAPIError(
                f"Failed to parse Speech API JSON response: {exc}"
            ) from exc

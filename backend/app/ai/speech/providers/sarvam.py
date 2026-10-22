"""Sarvam AI Speech-to-Text Provider (Saaras) for Indian Languages."""
import logging
from typing import Optional, Dict, Any
import httpx

from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.schemas import TranscriptionResult
from app.ai.speech.exceptions import (
    SpeechTimeoutError,
    SpeechAPIError,
)

logger = logging.getLogger(__name__)

# BCP-47 language code mappings for Sarvam Saaras
SARVAM_LANGUAGE_MAP = {
    "hindi": "hi-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "marathi": "mr-IN",
    "mr": "mr-IN",
    "mr-in": "mr-IN",
    "english": "en-IN",
    "en": "en-IN",
    "en-in": "en-IN",
}

# Reverse map Sarvam language codes to human-readable names
REVERSE_LANGUAGE_MAP = {
    "hi-IN": "Hindi",
    "mr-IN": "Marathi",
    "en-IN": "English",
    "bn-IN": "Bengali",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "gu-IN": "Gujarati",
    "ml-IN": "Malayalam",
    "pa-IN": "Punjabi",
    "od-IN": "Odia",
}


class SarvamSpeechProvider(SpeechToTextProvider):
    """
    Cloud REST API Speech-to-Text provider powered by Sarvam AI Saaras.
    Specialized for Hindi, Marathi, Indian English, and code-mixed speech.
    Communicates via direct REST API without local model downloads.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.sarvam.ai/speech-to-text",
        model: str = "saaras:v4",
        timeout: float = 20.0,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "sarvam"

    @property
    def api_endpoint_info(self) -> str:
        return f"Sarvam AI Saaras STT: {self.api_url} (model: {self.model})"

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes using Sarvam AI Saaras REST API.
        Handles authentication errors, rate limiting, timeouts, and multilingual detection.
        """
        self.validate_audio(audio_bytes, filename, content_type)

        if not self.api_key or self.api_key in ("YOUR_SARVAM_API_KEY", ""):
            raise SpeechAPIError(
                "Sarvam STT API key not configured or set to placeholder. Dispatcher manual listening required."
            )

        headers = {
            "api-subscription-key": self.api_key,
        }

        form_data: Dict[str, str] = {
            "model": self.model,
        }

        # Configure language code if hint matches known BCP-47
        if language_hint:
            hint_clean = language_hint.strip().lower()
            if hint_clean in SARVAM_LANGUAGE_MAP:
                form_data["language_code"] = SARVAM_LANGUAGE_MAP[hint_clean]

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
                f"Sarvam AI STT API timed out after {self.timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise SpeechAPIError(
                f"Network error communicating with Sarvam AI STT API: {exc}"
            ) from exc

        # Handle specific HTTP error status codes
        if response.status_code in (401, 403):
            raise SpeechAPIError(
                f"Sarvam AI STT authentication failed (HTTP {response.status_code}): Invalid or expired API subscription key."
            )
        elif response.status_code == 429:
            raise SpeechAPIError(
                "Sarvam AI STT rate limit exceeded (HTTP 429). Upstream quota reached."
            )
        elif response.status_code != 200:
            error_preview = response.text[:200]
            raise SpeechAPIError(
                f"Sarvam AI STT returned HTTP {response.status_code}: {error_preview}"
            )

        try:
            data = response.json()
            transcript_text = data.get("transcript", "").strip()
            raw_lang_code = data.get("language_code")
            detected_lang = REVERSE_LANGUAGE_MAP.get(raw_lang_code, raw_lang_code)

            # Determine confidence and clarity
            is_unclear = not transcript_text or len(transcript_text) < 4
            confidence = 0.95 if not is_unclear else 0.30

            return TranscriptionResult(
                text=transcript_text or "[Inaudible / Unclear audio]",
                detected_language=detected_lang or "unknown",
                duration_seconds=data.get("duration"),
                confidence=confidence,
                is_unclear=is_unclear,
                raw_metadata=data,
            )
        except Exception as exc:
            raise SpeechAPIError(
                f"Failed to parse Sarvam AI STT response payload: {exc}"
            ) from exc

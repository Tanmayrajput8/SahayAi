"""Mock Speech-to-Text provider for offline testing and local development."""
import logging
from typing import Optional

from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.schemas import TranscriptionResult
from app.ai.speech.exceptions import (
    SpeechTimeoutError,
    SpeechAPIError,
)

logger = logging.getLogger(__name__)


class MockSpeechProvider(SpeechToTextProvider):
    """
    Mock Speech-to-Text provider.
    Validates audio format and sizes, and simulates transcripts and error modes
    without downloading local models or requiring external API keys.
    """

    def __init__(
        self,
        simulate_timeout: bool = False,
        simulate_api_error: bool = False,
        simulate_unclear: bool = False,
    ):
        self.simulate_timeout = simulate_timeout
        self.simulate_api_error = simulate_api_error
        self.simulate_unclear = simulate_unclear

    @property
    def provider_name(self) -> str:
        return "mock_speech_provider"

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe mock audio bytes with full validation and test simulations."""
        # 1. Standard format and size validation
        self.validate_audio(audio_bytes, filename, content_type)

        # 2. Simulated failure triggers
        if self.simulate_timeout:
            raise SpeechTimeoutError("Simulated Speech API request timed out after 20.0s.")

        if self.simulate_api_error:
            raise SpeechAPIError("Simulated external speech API 500 Internal Server Error.")

        name_lower = filename.lower()

        if self.simulate_unclear or "unclear" in name_lower or "noise" in name_lower:
            return TranscriptionResult(
                text="[Muffled background siren noise... unintelligible whispering... ambulance...]",
                detected_language="unknown",
                duration_seconds=5.2,
                confidence=0.32,
                is_unclear=True,
                raw_metadata={"snr_db": 3.1, "status": "UNCLEAR"},
            )

        # 3. Multi-lingual mock transcripts based on filename or language hint
        if "hindi" in name_lower or language_hint == "hi":
            text = "यहाँ अंधेरी स्टेशन के पास बहुत बड़ा एक्सीडेंट हुआ है जल्दी एम्बुलेंस भेजो"
            lang = "hi"
        elif "marathi" in name_lower or language_hint == "mr":
            text = "दादर स्टेशन जवळ एक व्यक्ती बेशुद्ध पडली आहे, तातडीने मदत हवी आहे"
            lang = "mr"
        elif "cardiac" in name_lower:
            text = "Severe chest pain at Swargate depot, my father is having a heart attack please hurry"
            lang = "en"
        elif "kurla" in name_lower or "hinglish" in name_lower:
            text = "Bhai jaldi aao Kurla signal pe bike slip ho gayi bohot blood nikal raha hai"
            lang = "code-mixed"
        else:
            text = "Emergency! Severe two car accident at Marine Drive, passengers bleeding and need immediate help!"
            lang = "en"

        return TranscriptionResult(
            text=text,
            detected_language=lang,
            duration_seconds=12.4,
            confidence=0.92,
            is_unclear=False,
            raw_metadata={"model": "mock-whisper-v3", "audio_bytes": len(audio_bytes)},
        )

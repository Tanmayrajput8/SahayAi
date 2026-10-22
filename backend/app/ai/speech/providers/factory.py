"""Factory for Speech-to-Text provider instantiation."""
import logging
from typing import Optional

from app.core.config import settings
from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.providers.sarvam import SarvamSpeechProvider
from app.ai.speech.providers.external import ExternalSpeechProvider
from app.ai.speech.providers.mock import MockSpeechProvider

logger = logging.getLogger(__name__)


def get_speech_provider(provider_override: Optional[str] = None) -> SpeechToTextProvider:
    """
    Instantiate the configured SpeechToTextProvider.
    Supports:
    - 'sarvam': Sarvam AI Saaras STT API (Default for Indic/Hindi/Marathi speech)
    - 'groq' / 'external': Groq Whisper REST API
    - 'mock': Deterministic mock STT provider
    """
    choice = (provider_override or settings.SPEECH_PROVIDER or "sarvam").strip().lower()

    if choice == "sarvam":
        if not settings.SARVAM_API_KEY or settings.SARVAM_API_KEY == "YOUR_SARVAM_API_KEY":
            logger.warning("SARVAM_API_KEY not configured or set to placeholder. Falling back to MockSpeechProvider.")
            return MockSpeechProvider()
        return SarvamSpeechProvider(
            api_key=settings.SARVAM_API_KEY,
            api_url=settings.SARVAM_STT_URL,
            model=settings.SARVAM_STT_MODEL,
            timeout=settings.SARVAM_TIMEOUT_SECONDS,
        )

    if choice in ("groq", "external"):
        api_key = settings.STT_API_KEY or getattr(settings, "GROQ_API_KEY", "")
        if not api_key:
            logger.info("STT_API_KEY not configured. Using MockSpeechProvider for offline research prototype.")
            return MockSpeechProvider()
        return ExternalSpeechProvider(
            api_key=api_key,
            api_url=settings.STT_API_URL,
            model=settings.STT_MODEL,
            timeout=settings.STT_TIMEOUT_SECONDS,
        )

    return MockSpeechProvider()

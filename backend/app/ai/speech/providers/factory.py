"""Factory for Speech-to-Text provider instantiation."""
import logging
from typing import Optional

from app.core.config import settings
from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.providers.external import ExternalSpeechProvider
from app.ai.speech.providers.mock import MockSpeechProvider

logger = logging.getLogger(__name__)


def get_speech_provider(provider_override: Optional[str] = None) -> SpeechToTextProvider:
    """
    Instantiate the configured SpeechToTextProvider.
    If 'external' is selected but STT_API_KEY is empty,
    gracefully falls back to MockSpeechProvider.
    """
    choice = (provider_override or settings.SPEECH_PROVIDER or "mock").strip().lower()

    if choice == "external":
        if not settings.STT_API_KEY:
            logger.info("STT_API_KEY not configured. Using MockSpeechProvider for offline research prototype.")
            return MockSpeechProvider()
        return ExternalSpeechProvider(
            api_key=settings.STT_API_KEY,
            api_url=settings.STT_API_URL,
            model=settings.STT_MODEL,
            timeout=settings.STT_TIMEOUT_SECONDS,
        )

    return MockSpeechProvider()

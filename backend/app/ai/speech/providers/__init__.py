"""Speech-to-Text provider implementations."""
from app.ai.speech.providers.base import (
    SpeechToTextProvider,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_AUDIO_MIME_TYPES,
)
from app.ai.speech.providers.external import ExternalSpeechProvider
from app.ai.speech.providers.mock import MockSpeechProvider
from app.ai.speech.providers.factory import get_speech_provider

__all__ = [
    "SpeechToTextProvider",
    "ExternalSpeechProvider",
    "MockSpeechProvider",
    "get_speech_provider",
    "SUPPORTED_AUDIO_EXTENSIONS",
    "SUPPORTED_AUDIO_MIME_TYPES",
]

"""SahayAI Speech-to-Text Module."""
from app.ai.speech.providers.base import SpeechToTextProvider
from app.ai.speech.providers.external import ExternalSpeechProvider
from app.ai.speech.providers.mock import MockSpeechProvider
from app.ai.speech.providers.factory import get_speech_provider
from app.ai.speech.schemas import TranscriptionResult
from app.ai.speech.exceptions import (
    SpeechError,
    SpeechTimeoutError,
    SpeechAPIError,
    UnsupportedAudioFormatError,
    OversizedAudioError,
    EmptyAudioError,
    UnclearAudioError,
)
from app.ai.speech.service import process_audio_emergency

__all__ = [
    "SpeechToTextProvider",
    "ExternalSpeechProvider",
    "MockSpeechProvider",
    "get_speech_provider",
    "TranscriptionResult",
    "SpeechError",
    "SpeechTimeoutError",
    "SpeechAPIError",
    "UnsupportedAudioFormatError",
    "OversizedAudioError",
    "EmptyAudioError",
    "UnclearAudioError",
    "process_audio_emergency",
]

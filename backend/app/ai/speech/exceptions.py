"""Exceptions for Speech-to-Text operations."""


class SpeechError(Exception):
    """Base exception for speech-to-text processing."""
    pass


class SpeechTimeoutError(SpeechError):
    """Raised when speech-to-text API request times out."""
    pass


class SpeechAPIError(SpeechError):
    """Raised when external speech API returns an error."""
    pass


class UnsupportedAudioFormatError(SpeechError):
    """Raised when uploaded audio format is not supported."""
    pass


class OversizedAudioError(SpeechError):
    """Raised when uploaded audio exceeds maximum allowable size."""
    pass


class EmptyAudioError(SpeechError):
    """Raised when uploaded audio file has 0 bytes or no content."""
    pass


class UnclearAudioError(SpeechError):
    """Raised when audio is garbled or transcription is unintelligible."""
    pass

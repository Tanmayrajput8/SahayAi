"""Exceptions for the LLM intelligence layer."""


class LLMError(Exception):
    """Base exception for all LLM provider errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when an LLM upstream request times out."""
    pass


class LLMAPIError(LLMError):
    """Raised when an LLM upstream API returns a non-2xx status code or connection error."""
    pass


class LLMOutputFormatError(LLMError):
    """Raised when LLM output cannot be parsed into the required strict JSON schema."""
    pass

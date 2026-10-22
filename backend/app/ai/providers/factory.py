"""Factory to instantiate the configured LLM provider."""
import logging
from typing import Optional

from app.core.config import settings
from app.ai.providers.base import LLMProvider
from app.ai.providers.grok import GrokProvider
from app.ai.providers.mock import MockProvider

logger = logging.getLogger(__name__)


def get_llm_provider(provider_override: Optional[str] = None) -> LLMProvider:
    """
    Retrieve the configured LLMProvider instance.
    Supports 'groq', 'grok', and 'mock'. If 'groq' or 'grok' is configured without
    an API key, it logs a warning and gracefully defaults to MockProvider.
    """
    choice = (provider_override or settings.LLM_PROVIDER or "groq").strip().lower()

    if choice in ("groq", "grok"):
        api_key = settings.GROQ_API_KEY or settings.GROK_API_KEY
        api_url = settings.GROQ_API_URL if choice == "groq" else settings.GROK_API_URL
        model = settings.GROQ_MODEL if choice == "groq" else settings.GROK_MODEL

        if not api_key:
            logger.warning(
                "%s_API_KEY is empty. Falling back to MockProvider for offline research prototype.",
                choice.upper(),
            )
            return MockProvider()

        return GrokProvider(
            api_key=api_key,
            api_url=api_url,
            model=model,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    return MockProvider()

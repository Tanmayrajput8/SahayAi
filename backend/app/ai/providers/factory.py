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
    Supports 'grok' and 'mock'. If 'grok' is configured without an API key,
    it logs a warning and gracefully defaults to MockProvider.
    """
    choice = (provider_override or settings.LLM_PROVIDER or "mock").strip().lower()

    if choice == "grok":
        if not settings.GROK_API_KEY:
            logger.warning("GROK_API_KEY is empty. Falling back to MockProvider for offline research prototype.")
            return MockProvider()
        return GrokProvider(
            api_key=settings.GROK_API_KEY,
            api_url=settings.GROK_API_URL,
            model=settings.GROK_MODEL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=settings.LLM_MAX_RETRIES,
        )

    return MockProvider()

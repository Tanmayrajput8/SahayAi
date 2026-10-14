"""Factory for obtaining EmbeddingProvider instances."""
from typing import Optional
from app.core.config import settings
from app.ai.rag.embeddings.base import EmbeddingProvider
from app.ai.rag.embeddings.mock import MockEmbeddingProvider
from app.ai.rag.embeddings.external import ExternalEmbeddingProvider


def get_embedding_provider(provider_type: Optional[str] = None) -> EmbeddingProvider:
    """Returns configured or specified embedding provider."""
    p_type = (provider_type or settings.EMBEDDING_PROVIDER or "mock").lower()

    if p_type in ("external", "openai", "api"):
        return ExternalEmbeddingProvider(
            api_key=settings.EMBEDDING_API_KEY,
            api_url=settings.EMBEDDING_API_URL,
            model=settings.EMBEDDING_MODEL,
            timeout_seconds=settings.EMBEDDING_TIMEOUT_SECONDS,
        )
    return MockEmbeddingProvider()

"""External REST Embedding Provider with Automatic Mock Fallback."""
import logging
from typing import List, Optional
import httpx

from app.ai.rag.embeddings.base import EmbeddingProvider
from app.ai.rag.embeddings.mock import MockEmbeddingProvider

logger = logging.getLogger(__name__)


class ExternalEmbeddingProvider(EmbeddingProvider):
    """
    Client for external Embedding REST APIs (e.g., OpenAI text-embedding-3-small, Grok).
    Uses HTTP REST endpoint over network.
    Automatically falls back to MockEmbeddingProvider if API is unavailable or key is unset.
    """

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "https://api.openai.com/v1/embeddings",
        model: str = "text-embedding-3-small",
        timeout_seconds: float = 10.0,
        dimension: int = 1536,
    ):
        self.api_key = api_key.strip()
        self.api_url = api_url
        self.model = model
        self.timeout = timeout_seconds
        self._dim = dimension
        self._fallback = MockEmbeddingProvider(dimension=dimension)

    @property
    def provider_name(self) -> str:
        return f"external_embedding_{self.model}"

    @property
    def dimension(self) -> int:
        return self._dim

    def get_embedding(self, text: str) -> List[float]:
        results = self.get_embeddings([text])
        return results[0]

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            logger.info("No embedding API key provided. Using MockEmbeddingProvider.")
            return self._fallback.get_embeddings(texts)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": texts,
            "model": self.model,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.api_url, json=payload, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                embeddings_data = data.get("data", [])
                embeddings_data.sort(key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in embeddings_data]
            else:
                logger.warning(
                    "External embedding API returned HTTP %d: %s. Falling back to mock.",
                    resp.status_code,
                    resp.text[:120],
                )
                return self._fallback.get_embeddings(texts)

        except Exception as exc:
            logger.warning("External embedding API error: %s. Falling back to mock.", exc)
            return self._fallback.get_embeddings(texts)

"""Lightweight In-Memory Vector Store with Cosine Similarity Retrieval.

Stores document chunks with embeddings, source provenance, and metadata.
Calculates exact cosine similarity without heavy dependencies (FAISS, Chroma, PyTorch).
"""
import math
import logging
from typing import List, Dict, Any, Optional
from app.ai.rag.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine similarity between two numeric vectors."""
    if len(v1) != len(v2) or not v1:
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 < 1e-9 or norm2 < 1e-9:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm1 * norm2)))


class LightweightVectorStore:
    """
    Lightweight local vector storage for unstructured emergency knowledge chunks.
    Maintains chunk IDs, document IDs, embeddings, sources, metadata, and texts.
    """

    def __init__(self):
        self._chunks: List[Dict[str, Any]] = []

    def count(self) -> int:
        return len(self._chunks)

    def clear(self):
        self._chunks.clear()

    def add_chunk(
        self,
        chunk_id: str,
        document_id: str,
        title: str,
        text: str,
        source: str,
        category: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Add a single pre-embedded chunk into the store."""
        # Replace if chunk_id already exists to prevent duplicates
        self._chunks = [c for c in self._chunks if c["chunk_id"] != chunk_id]
        self._chunks.append({
            "chunk_id": chunk_id,
            "document_id": document_id,
            "title": title,
            "text": text,
            "source": source,
            "category": category,
            "embedding": embedding,
            "metadata": metadata or {},
        })

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 3,
        similarity_threshold: float = 0.25,
        category_filter: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        """
        Execute top-K cosine similarity semantic retrieval against stored chunks.
        """
        if not self._chunks:
            return []

        scored_chunks = []
        for c in self._chunks:
            if category_filter and c["category"].lower() != category_filter.lower():
                continue

            score = cosine_similarity(query_embedding, c["embedding"])
            # Normalize [-1, 1] cosine score to [0, 1] range
            normalized_score = max(0.0, min(1.0, (score + 1.0) / 2.0))

            if normalized_score >= similarity_threshold:
                scored_chunks.append((c, normalized_score))

        # Sort descending by similarity score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        results: List[RetrievedChunk] = []
        for c, score in scored_chunks[:top_k]:
            results.append(
                RetrievedChunk(
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    title=c["title"],
                    text=c["text"],
                    source=c["source"],
                    category=c["category"],
                    similarity_score=round(score, 4),
                    metadata=c["metadata"],
                )
            )

        return results

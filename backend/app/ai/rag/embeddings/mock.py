"""Deterministic Mock Embedding Provider for Development and Testing."""
import hashlib
import math
import logging
from typing import List
from app.ai.rag.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

# Core semantic concept clusters for emergency domain to ensure meaningful cosine similarities
SEMANTIC_ANCHORS = {
    "cardiac": ["cardiac", "heart", "chest", "angina", "coronary", "stemi", "chaati", "chhati", "pain", "arrest", "attack"],
    "trauma": ["trauma", "accident", "fracture", "bleeding", "hemorrhage", "crash", "collision", "fall", "injury", "apghat", "durghatna", "maramari"],
    "burns": ["burn", "fire", "scald", "smoke", "flame", "thermal", "chemical", "aag", "dhuan", "blister"],
    "respiratory": ["breathing", "breath", "asthma", "copd", "choking", "gasping", "stridor", "dyspnea", "shwas", "dum"],
    "stroke": ["stroke", "paralysis", "facial", "slurred", "droop", "arm", "weakness", "cva", "fast", "pakshaghat"],
    "pediatric": ["child", "pediatric", "infant", "baby", "toddler", "balak", "mulga", "mulgi", "bachha"],
    "ambulance": ["ambulance", "als", "bls", "paramedic", "ventilator", "defibrillator", "oxygen", "first aid", "transport"],
    "hospital": ["hospital", "icu", "bed", "doctor", "trauma center", "emergency department", "clinic", "ward"],
}


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Lightweight, deterministic embedding provider that computes normalized dense vectors
    using semantic feature projection and subword hash buckets.
    Eliminates dependency on PyTorch / sentence-transformers / GPU.
    """

    def __init__(self, dimension: int = 128):
        self._dim = dimension

    @property
    def provider_name(self) -> str:
        return "mock_embedding"

    @property
    def dimension(self) -> int:
        return self._dim

    def get_embedding(self, text: str) -> List[float]:
        vec = [0.0] * self._dim
        clean_text = (text or "").lower()
        words = clean_text.split()

        # 1. Project onto semantic anchor dimensions (dimensions 0 to 63)
        anchor_keys = list(SEMANTIC_ANCHORS.keys())
        for idx, (anchor, keywords) in enumerate(SEMANTIC_ANCHORS.items()):
            dim_idx = idx * 8
            for kw in keywords:
                if kw in clean_text:
                    for offset in range(8):
                        target = (dim_idx + offset) % 64
                        vec[target] += 1.5

        # 2. Project subword character n-grams across dimensions 64 to 127
        for word in words:
            # Word-level hash
            h_word = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            slot = 64 + (h_word % (self._dim - 64))
            vec[slot] += 1.0

            # 3-gram subwords
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    ngram = word[i : i + 3]
                    h_ng = int(hashlib.sha256(ngram.encode("utf-8")).hexdigest(), 16)
                    ng_slot = 64 + (h_ng % (self._dim - 64))
                    vec[ng_slot] += 0.4

        # 3. L2 Normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-8:
            return [x / norm for x in vec]
        else:
            # Default fallback unit vector
            val = 1.0 / math.sqrt(self._dim)
            return [val] * self._dim

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.get_embedding(t) for t in texts]

"""Pydantic schemas for RAG-based clinical verification."""
import enum
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class RAGVerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTING = "CONFLICTING"


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    text: str
    source: str
    category: str
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RAGVerificationResult(BaseModel):
    status: RAGVerificationStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    retrieved_evidence: List[RetrievedChunk] = Field(default_factory=list)
    source_reference: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_used: str = "mock-rag-verifier"
    verified_fields: List[str] = Field(default_factory=list)
    conflicting_fields: List[str] = Field(default_factory=list)
    protocol_code: Optional[str] = None

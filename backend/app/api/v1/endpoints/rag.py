"""Endpoints for Retrieval-Augmented Generation (RAG) Clinical Verification."""
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.case import Case
from app.ai.rag.schemas import RAGVerificationResult
from app.ai.rag.service import (
    verify_with_rag,
    execute_case_rag_verification,
    load_and_index_knowledge_base,
    get_vector_store,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class DirectVerifyRequest(BaseModel):
    query_text: str = Field(..., description="Emergency narrative or symptoms")
    reported_severity: Optional[str] = Field(default=None, description="Reported severity: CRITICAL, HIGH, MODERATE, LOW")
    reported_ambulance: Optional[str] = Field(default=None, description="Reported ambulance requirement: ALS, BLS")
    emergency_type: Optional[str] = Field(default=None, description="Cardiac, Trauma, Burns, Respiratory, etc.")


@router.post(
    "/verify",
    response_model=RAGVerificationResult,
    summary="Direct RAG Clinical Verification",
    description="Retrieve evidence chunks from unstructured clinical guidelines and verify emergency triage parameters.",
)
def verify_direct_endpoint(payload: DirectVerifyRequest) -> RAGVerificationResult:
    return verify_with_rag(
        query_text=payload.query_text,
        reported_severity=payload.reported_severity,
        reported_ambulance=payload.reported_ambulance,
        emergency_type=payload.emergency_type,
    )


@router.post(
    "/cases/{case_id}/verify",
    response_model=RAGVerificationResult,
    summary="Verify Case with RAG Knowledge",
    description="Retrieve evidence for an emergency case, persist VerificationResult in database, and log audit trail.",
)
def verify_case_endpoint(case_id: str, db: Session = Depends(get_db)) -> RAGVerificationResult:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Case '{case_id}' not found."},
        )

    _, rag_result = execute_case_rag_verification(case_id=case_id, db=db)
    return rag_result


@router.get(
    "/status",
    summary="RAG Vector Store Status",
    description="Returns indexing status and number of indexed clinical knowledge chunks.",
)
def rag_status_endpoint() -> Dict[str, Any]:
    store = get_vector_store()
    return {
        "status": "active",
        "total_chunks_indexed": store.count(),
        "vector_store": "LightweightVectorStore (in-memory cosine)",
    }


@router.post(
    "/reindex",
    summary="Reindex Clinical Knowledge Base",
    description="Reload and chunk all documents from the knowledge base directory.",
)
def rag_reindex_endpoint() -> Dict[str, Any]:
    total = load_and_index_knowledge_base(force_reindex=True)
    return {
        "status": "reindexed",
        "total_chunks": total,
    }

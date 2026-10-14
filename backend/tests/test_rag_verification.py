"""Comprehensive Test Suite for Part 11: RAG-based Verification."""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.seed import seed_database
from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType, InputModality
from app.models.extracted_info import ExtractedInfo
from app.models.ai_decision import AIDecision
from app.models.verification import VerificationResult, VerificationStatus
from app.models.audit import AuditLog, AuditStage
from app.ai.rag.schemas import RAGVerificationStatus, RAGVerificationResult
from app.ai.rag.embeddings.mock import MockEmbeddingProvider
from app.ai.rag.embeddings.external import ExternalEmbeddingProvider
from app.ai.rag.vector_store import LightweightVectorStore, cosine_similarity
from app.ai.rag.service import (
    load_and_index_knowledge_base,
    get_vector_store,
    verify_with_rag,
    execute_case_rag_verification,
)
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_indexed():
    """Ensure knowledge base is indexed for tests."""
    load_and_index_knowledge_base(force_reindex=False)


@pytest.fixture
def db_session():
    db = SessionLocal()
    seed_database(db)
    try:
        yield db
    finally:
        db.close()


def test_vector_store_cosine_similarity():
    """Verify cosine similarity calculation."""
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    assert cosine_similarity(v1, v2) == 1.0

    v3 = [0.0, 1.0, 0.0]
    assert cosine_similarity(v1, v3) == 0.0


def test_mock_embedding_provider_multilingual_similarity():
    """Verify mock embeddings generate high similarity for related multilingual cardiac concepts."""
    provider = MockEmbeddingProvider()
    e_en = provider.get_embedding("Severe crushing chest pain and heart attack")
    e_hi = provider.get_embedding("Bahut tez chaati me dard aur paseena")
    e_mr = provider.get_embedding("Chhati madhe bhayanak vedna ahe")
    e_unrelated = provider.get_embedding("Lost my library book yesterday in garden")

    sim_hi = cosine_similarity(e_en, e_hi)
    sim_mr = cosine_similarity(e_en, e_mr)
    sim_unrelated = cosine_similarity(e_en, e_unrelated)

    assert sim_hi > sim_unrelated
    assert sim_mr > sim_unrelated


def test_rag_successful_cardiac_retrieval():
    """Verify successful retrieval and verification for cardiac emergency matching protocol."""
    res = verify_with_rag(
        query_text="Severe crushing chest pain radiating to left arm with cold sweating",
        reported_severity="CRITICAL",
        reported_ambulance="ALS",
        emergency_type="Cardiac Emergency",
    )
    assert res.status == RAGVerificationStatus.VERIFIED
    assert res.confidence >= 0.70
    assert len(res.retrieved_evidence) >= 1
    assert any("cardiac" in c.category.lower() or "cardiac" in c.title.lower() for c in res.retrieved_evidence)
    assert "PROTO-CARD" in (res.protocol_code or "")


def test_rag_conflicting_evidence_detection():
    """Verify RAG flags CONFLICTING when lethal cardiac emergency is triaged as low-tier BLS."""
    res = verify_with_rag(
        query_text="Crushing chest pain radiating to jaw and diaphoresis",
        reported_severity="LOW",
        reported_ambulance="BLS",
        emergency_type="Cardiac",
    )
    assert res.status == RAGVerificationStatus.CONFLICTING
    assert len(res.conflicting_fields) >= 1
    assert "ALS" in res.explanation or "dangerously" in res.explanation.lower()


def test_rag_unavailable_evidence_for_out_of_domain_query():
    """Verify RAG returns UNAVAILABLE when query is outside clinical knowledge."""
    res = verify_with_rag(
        query_text="Alien spacecraft hovering over mountain with glowing purple lights",
        reported_severity="LOW",
        reported_ambulance="BLS",
        similarity_threshold=0.85,
    )
    assert res.status == RAGVerificationStatus.UNAVAILABLE
    assert res.confidence <= 0.40


def test_external_embedding_api_failure_fallback():
    """Verify external embedding provider falls back to mock if network fails."""
    ext = ExternalEmbeddingProvider(api_key="sk-test-key", api_url="https://failing.api/embeddings")
    with patch("httpx.Client.post", side_effect=Exception("API connection timeout")):
        emb = ext.get_embedding("Test medical narrative")

    assert len(emb) == ext.dimension
    assert sum(x * x for x in emb) > 0.0


def test_execute_case_rag_verification_in_db(db_session: Session):
    """Verify end-to-end case RAG verification persists in DB with AuditLog."""
    case = Case(
        raw_text="Major vehicle crash with head injury and compound fracture",
        modality=InputModality.TEXT.value,
        status=CaseStatus.TRIAGED,
        priority=SeverityLevel.CRITICAL,
    )
    db_session.add(case)
    db_session.flush()

    db_session.add(ExtractedInfo(
        case_id=case.id,
        emergency_type="Road Traffic Accident",
        symptoms=["severe bleeding", "fracture", "head trauma"],
    ))
    db_session.add(AIDecision(
        case_id=case.id,
        severity_assessment=SeverityLevel.CRITICAL,
        recommended_ambulance_type=AmbulanceType.ALS,
        clinical_rationale="High kinetic impact trauma.",
        confidence_score=0.90,
    ))
    db_session.commit()

    verif_record, rag_result = execute_case_rag_verification(case_id=case.id, db=db_session)

    assert verif_record.id is not None
    assert verif_record.status == VerificationStatus.VERIFIED
    assert verif_record.verification_score >= 0.70
    assert "PROTO-TRAUMA" in (verif_record.protocol_code or "")

    # Verify audit log
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.stage == AuditStage.RAG_VERIFICATION)
        .first()
    )
    assert audit is not None
    assert "RAG_VERIFICATION_VERIFIED" in audit.action


def test_api_rag_verify_endpoint():
    """Verify POST /api/v1/rag/verify REST endpoint."""
    payload = {
        "query_text": "Sudden facial droop, arm weakness, and slurred speech",
        "reported_severity": "HIGH",
        "reported_ambulance": "ALS",
        "emergency_type": "Stroke",
    }
    resp = client.post("/api/v1/rag/verify", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("VERIFIED", "CONFLICTING")
    assert len(data["retrieved_evidence"]) >= 1
    assert data["model_used"] is not None


def test_api_rag_status_endpoint():
    """Verify GET /api/v1/rag/status REST endpoint."""
    resp = client.get("/api/v1/rag/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["total_chunks_indexed"] >= 10

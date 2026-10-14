"""RAG Verification Service orchestrating Document Loading, Chunking, Vector Storage, Semantic Retrieval, and Clinical Verification."""
import os
import glob
import logging
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.case import Case, SeverityLevel, AmbulanceType
from app.models.verification import VerificationResult, VerificationStatus
from app.models.audit import AuditLog, AuditStage
from app.ai.rag.schemas import RAGVerificationResult, RAGVerificationStatus, RetrievedChunk
from app.ai.rag.embeddings.base import EmbeddingProvider
from app.ai.rag.embeddings.factory import get_embedding_provider
from app.ai.rag.vector_store import LightweightVectorStore

logger = logging.getLogger(__name__)

# Global singleton in-memory vector store for unstructured knowledge base
_vector_store = LightweightVectorStore()
_is_indexed = False


def chunk_document(doc_id: str, title: str, category: str, source: str, content: str) -> List[Dict[str, Any]]:
    """
    Chunk document by markdown headings and paragraphs, preserving section context.
    """
    chunks: List[Dict[str, Any]] = []
    lines = content.split("\n")
    current_section = title
    current_lines: List[str] = []
    chunk_index = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_lines:
                chunk_text = "\n".join(current_lines).strip()
                if len(chunk_text) > 30:
                    chunks.append({
                        "chunk_id": f"{doc_id}_chunk_{chunk_index}",
                        "document_id": doc_id,
                        "title": f"{title} - {current_section}",
                        "text": chunk_text,
                        "source": source,
                        "category": category,
                        "metadata": {"section": current_section},
                    })
                    chunk_index += 1
                current_lines = []
            current_section = stripped.replace("## ", "")
            current_lines.append(stripped)
        else:
            if stripped:
                current_lines.append(stripped)

    # Add final trailing chunk
    if current_lines:
        chunk_text = "\n".join(current_lines).strip()
        if len(chunk_text) > 30:
            chunks.append({
                "chunk_id": f"{doc_id}_chunk_{chunk_index}",
                "document_id": doc_id,
                "title": f"{title} - {current_section}",
                "text": chunk_text,
                "source": source,
                "category": category,
                "metadata": {"section": current_section},
            })

    return chunks


def load_and_index_knowledge_base(
    kb_dir: Optional[str] = None,
    embedding_provider: Optional[EmbeddingProvider] = None,
    force_reindex: bool = False,
) -> int:
    """
    Ingest, chunk, and embed all knowledge base documents into the vector store.
    """
    global _is_indexed
    if _is_indexed and not force_reindex:
        return _vector_store.count()

    if embedding_provider is None:
        embedding_provider = get_embedding_provider()

    directory = kb_dir or settings.KNOWLEDGE_BASE_DIR
    if not os.path.exists(directory):
        logger.warning("Knowledge base directory '%s' does not exist. Creating it.", directory)
        os.makedirs(directory, exist_ok=True)
        return 0

    doc_files = glob.glob(os.path.join(directory, "*.md")) + glob.glob(os.path.join(directory, "*.txt"))
    logger.info("Ingesting %d knowledge base documents from '%s'...", len(doc_files), directory)

    _vector_store.clear()
    total_chunks = 0

    for file_path in doc_files:
        doc_name = os.path.splitext(os.path.basename(file_path))[0]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            title = doc_name.replace("_", " ").title()
            category = "GENERAL"
            source = "SahayAI Knowledge Base"

            for line in content.split("\n"):
                if line.startswith("Category:"):
                    category = line.replace("Category:", "").strip()
                elif line.startswith("Source:"):
                    source = line.replace("Source:", "").strip()
                elif line.startswith("# ") and title == doc_name.replace("_", " ").title():
                    title = line.replace("# ", "").strip()

            chunks = chunk_document(doc_name, title, category, source, content)
            if not chunks:
                continue

            texts = [c["text"] for c in chunks]
            embeddings = embedding_provider.get_embeddings(texts)

            for c, emb in zip(chunks, embeddings):
                _vector_store.add_chunk(
                    chunk_id=c["chunk_id"],
                    document_id=c["document_id"],
                    title=c["title"],
                    text=c["text"],
                    source=c["source"],
                    category=c["category"],
                    embedding=emb,
                    metadata=c["metadata"],
                )
                total_chunks += 1

        except Exception as exc:
            logger.error("Failed to load knowledge document '%s': %s", file_path, exc)

    _is_indexed = True
    logger.info("Knowledge base indexing completed: %d total chunks stored.", total_chunks)
    return total_chunks


def get_vector_store() -> LightweightVectorStore:
    """Ensure knowledge base is indexed and return active vector store."""
    if not _is_indexed:
        load_and_index_knowledge_base()
    return _vector_store


def verify_with_rag(
    query_text: str,
    reported_severity: Optional[str] = None,
    reported_ambulance: Optional[str] = None,
    emergency_type: Optional[str] = None,
    embedding_provider: Optional[EmbeddingProvider] = None,
    top_k: int = 3,
    similarity_threshold: float = 0.35,
) -> RAGVerificationResult:
    """
    Execute semantic retrieval and evidence-backed clinical verification.

    Statuses:
    - VERIFIED: Retrieved clinical evidence validates the severity/ambulance triage.
    - CONFLICTING: Evidence conflicts with reported severity or ambulance type (e.g. ALS needed for cardiac, but BLS was chosen).
    - UNAVAILABLE: Insufficient relevant evidence found in knowledge base.
    """
    if embedding_provider is None:
        embedding_provider = get_embedding_provider()

    store = get_vector_store()
    if store.count() == 0:
        return RAGVerificationResult(
            status=RAGVerificationStatus.UNAVAILABLE,
            confidence=0.0,
            explanation="Clinical knowledge base is empty. Verification unavailable.",
            retrieved_evidence=[],
            model_used=embedding_provider.provider_name,
        )

    # 1. Embed Query
    query_embedding = embedding_provider.get_embedding(query_text)

    # 2. Retrieve Top-K Context Chunks
    retrieved: List[RetrievedChunk] = store.search(
        query_embedding=query_embedding,
        top_k=top_k,
        similarity_threshold=similarity_threshold,
    )

    if not retrieved:
        return RAGVerificationResult(
            status=RAGVerificationStatus.UNAVAILABLE,
            confidence=0.30,
            explanation=f"No relevant clinical guidance found exceeding {similarity_threshold:.2f} similarity threshold.",
            retrieved_evidence=[],
            model_used=embedding_provider.provider_name,
        )

    # 3. Analyze Evidence Against Clinical Presentation
    combined_evidence_text = " ".join([c.text.lower() for c in retrieved])
    top_chunk = retrieved[0]
    avg_score = sum(c.similarity_score for c in retrieved) / len(retrieved)

    # Detect protocol code
    proto_code = "PROTO-GEN"
    for c in retrieved:
        if "proto-" in c.title.lower():
            words = c.title.split()
            for w in words:
                if "proto-" in w.lower():
                    proto_code = w.strip("():")
                    break

    # Clinical Conflict Check
    conflicts: List[str] = []
    verified_fields: List[str] = ["symptoms"]

    # Check 1: ALS vs BLS Conflict
    requires_als = "als" in combined_evidence_text or "advanced life support" in combined_evidence_text
    requires_bls_only = "bls only" in combined_evidence_text

    rep_amb_upper = (reported_ambulance or "").upper()
    rep_sev_upper = (reported_severity or "").upper()

    if requires_als and rep_amb_upper == "BLS":
        conflicts.append(f"Protocol '{proto_code}' mandates ALS equipment (ventilator/defibrillator); caller/triage suggested BLS.")
    elif requires_als and rep_amb_upper == "ALS":
        verified_fields.append("ambulance_type")

    # Check 2: Critical Severity Conflict
    evidence_mentions_critical = any(kw in combined_evidence_text for kw in ("cardiac arrest", "respiratory failure", "third degree", "unconscious", "lethal"))
    if evidence_mentions_critical and rep_sev_upper in ("LOW", "MODERATE"):
        conflicts.append(f"Clinical evidence indicates life-threatening risk; reported severity '{reported_severity}' is dangerously underestimated.")
    elif not conflicts and reported_severity:
        verified_fields.append("severity")

    # Formulate Result
    if conflicts:
        status = RAGVerificationStatus.CONFLICTING
        confidence = round(max(0.40, avg_score), 2)
        explanation = f"Conflicting clinical evidence detected: {'; '.join(conflicts)}"
    else:
        status = RAGVerificationStatus.VERIFIED
        confidence = round(min(0.98, max(0.70, avg_score)), 2)
        explanation = (
            f"Clinical evidence from '{top_chunk.title}' corroborates "
            f"triage profile ({reported_severity or 'assessed'}, {reported_ambulance or 'ALS/BLS'}). "
            f"Protocol: {proto_code}."
        )

    return RAGVerificationResult(
        status=status,
        confidence=confidence,
        explanation=explanation,
        retrieved_evidence=retrieved,
        source_reference=top_chunk.source,
        model_used=embedding_provider.provider_name,
        verified_fields=verified_fields,
        conflicting_fields=conflicts,
        protocol_code=proto_code,
    )


def execute_case_rag_verification(
    case_id: str,
    db: Session,
    embedding_provider: Optional[EmbeddingProvider] = None,
) -> Tuple[VerificationResult, RAGVerificationResult]:
    """
    Run RAG verification for an existing emergency case, persist VerificationResult in DB,
    and log immutable AuditLog.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case with ID '{case_id}' does not exist.")

    # Formulate query text from raw text, symptoms, and emergency type
    ext = case.extracted_info
    parts = [case.raw_text]
    if ext:
        if ext.emergency_type:
            parts.append(ext.emergency_type)
        if ext.symptoms:
            parts.append(" ".join(ext.symptoms))
    query_text = " ".join(parts)

    latest_decision = case.ai_decisions[-1] if case.ai_decisions else None
    rep_sev = latest_decision.severity_assessment.value if latest_decision else case.priority.value
    rep_amb = latest_decision.recommended_ambulance_type.value if latest_decision else None

    # Execute verification
    rag_res = verify_with_rag(
        query_text=query_text,
        reported_severity=rep_sev,
        reported_ambulance=rep_amb,
        emergency_type=ext.emergency_type if ext else None,
        embedding_provider=embedding_provider,
    )

    # Persist or update VerificationResult
    verif = (
        db.query(VerificationResult)
        .filter(VerificationResult.case_id == case.id)
        .first()
    )
    if not verif:
        verif = VerificationResult(case_id=case.id)
        db.add(verif)

    # Map status enum
    mapped_status = VerificationStatus.VERIFIED
    if rag_res.status == RAGVerificationStatus.CONFLICTING:
        mapped_status = VerificationStatus.CONFLICTING
    elif rag_res.status == RAGVerificationStatus.UNAVAILABLE:
        mapped_status = VerificationStatus.UNAVAILABLE

    verif.protocol_code = rag_res.protocol_code or "PROTO-GEN"
    verif.status = mapped_status
    verif.verified_fields = rag_res.verified_fields
    verif.conflicting_fields = rag_res.conflicting_fields
    verif.rag_evidence = rag_res.explanation + "\n\nRetrieved Chunks:\n" + "\n---\n".join([f"[{c.title}] {c.text}" for c in rag_res.retrieved_evidence])
    verif.verification_score = rag_res.confidence

    # Immutable Audit Log
    audit = AuditLog(
        case_id=case.id,
        stage=AuditStage.RAG_VERIFICATION,
        actor=f"RAG_VERIFIER_{rag_res.model_used.upper()}",
        action=f"RAG_VERIFICATION_{rag_res.status.value}",
        details={
            "status": rag_res.status.value,
            "confidence": rag_res.confidence,
            "protocol_code": rag_res.protocol_code,
            "verified_fields": rag_res.verified_fields,
            "conflicting_fields": rag_res.conflicting_fields,
            "retrieved_count": len(rag_res.retrieved_evidence),
            "sources": [c.source for c in rag_res.retrieved_evidence],
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(verif)
    return verif, rag_res

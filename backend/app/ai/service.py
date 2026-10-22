"""Core AI Intelligence Service orchestrating LLMProvider triage and fail-safe routing."""
import time
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatus, SeverityLevel
from app.models.extracted_info import ExtractedInfo
from app.models.ai_decision import AIDecision
from app.models.human_review import HumanReview, ReviewStatus
from app.models.audit import AuditLog, AuditStage
from app.models.verification import VerificationResult, VerificationStatus
from app.models.duplicate import DuplicateRelationship
from app.models.location import Location, GeocodingStatus
from app.ai.providers.base import LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.ai.schemas import EmergencyExtractionResult
from app.ai.triage_engine import evaluate_hybrid_triage
from app.ai.geocoding import process_case_geocoding, GeocodingProvider
from app.services.duplicate_detection import run_duplicate_detection, DuplicateState

logger = logging.getLogger(__name__)


def process_case_extraction(
    case_id: str,
    db: Session,
    provider: Optional[LLMProvider] = None,
    geocoding_provider: Optional[GeocodingProvider] = None,
) -> Case:
    """
    Process an emergency case through the LLM intelligence layer.

    Guarantees:
    - Communicates strictly via LLMProvider abstraction.
    - If the LLM fails (timeout, network error, malformed JSON):
      DO NOT lose the case. Marks extraction failure, escalates priority for safety,
      and routes the case directly to human review.
    - If confidence is low or information is contradictory/missing:
      Routes the case to Human Review.
    - If extraction succeeds with high confidence:
      Marks case as TRIAGED and creates explainable clinical triage record.
    """
    case: Optional[Case] = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case with ID '{case_id}' does not exist.")

    if provider is None:
        provider = get_llm_provider()

    start_time = time.time()
    try:
        # Execute LLM extraction
        result: EmergencyExtractionResult = provider.extract_emergency_info(
            raw_text=case.raw_text,
            modality=case.modality,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # 1. Update or create ExtractedInfo record
        extracted = case.extracted_info
        if not extracted:
            extracted = ExtractedInfo(case_id=case.id)
            db.add(extracted)

        extracted.emergency_type = result.emergency_type
        extracted.symptoms = result.symptoms
        extracted.extracted_location_text = result.location
        extracted.patient_count = result.patient_count
        extracted.conscious_status = result.conscious_status
        extracted.breathing_status = result.breathing_status
        extracted.raw_llm_output = result.model_dump()
        extracted.extraction_confidence = result.confidence_score

        # 2. Hybrid Triage: LLM Understanding + Deterministic Backend Validation
        hybrid = evaluate_hybrid_triage(extraction=result, raw_text=case.raw_text)

        extracted.raw_llm_output = {
            **result.model_dump(),
            "hybrid_triage": {
                "final_severity": hybrid.final_severity.value,
                "final_ambulance": hybrid.final_ambulance.value,
                "ai_suggested_severity": hybrid.ai_suggested_severity.value,
                "ai_suggested_ambulance": hybrid.ai_suggested_ambulance.value,
                "deterministic_severity": hybrid.deterministic_severity.value,
                "deterministic_ambulance": hybrid.deterministic_ambulance.value,
                "has_conflict": hybrid.has_conflict,
                "conflict_reason": hybrid.conflict_reason,
                "disclaimer": hybrid.disclaimer,
            },
        }

        # 3. Record explainable AI + deterministic clinical decision
        decision = AIDecision(
            case_id=case.id,
            model_name=provider.provider_name,
            severity_assessment=hybrid.final_severity,
            recommended_ambulance_type=hybrid.final_ambulance,
            clinical_rationale=hybrid.clinical_rationale,
            confidence_score=result.confidence_score,
            latency_ms=latency_ms,
            ai_suggested_severity=hybrid.ai_suggested_severity.value,
            ai_suggested_ambulance=hybrid.ai_suggested_ambulance.value,
            deterministic_severity=hybrid.deterministic_severity.value,
            deterministic_ambulance=hybrid.deterministic_ambulance.value,
            has_conflict=hybrid.has_conflict,
            conflict_reason=hybrid.conflict_reason,
            decision_type=hybrid.decision_type,
            disclaimer=hybrid.disclaimer,
        )
        db.add(decision)

        # 4. Update Case properties
        case.language = result.detected_language
        case.priority = hybrid.final_severity

        # 5. Clinical Protocol Verification
        verif_status = VerificationStatus.CONFLICTING if (result.is_contradictory or hybrid.has_conflict) else VerificationStatus.VERIFIED
        verif_score = 0.50 if (result.is_contradictory or hybrid.has_conflict) else 1.0
        proto_code = f"PROTO-{result.emergency_type[:4].upper()}" if result.emergency_type else "PROTO-GEN"
        verification = VerificationResult(
            case_id=case.id,
            protocol_code=proto_code,
            status=verif_status,
            verified_fields=["emergency_type", "severity", "ambulance_requirement"],
            conflicting_fields=["conflict_reason"] if hybrid.has_conflict else (["contradiction_notes"] if result.is_contradictory else []),
            rag_evidence=hybrid.clinical_rationale,
            verification_score=verif_score,
        )
        db.add(verification)

        audit_verif = AuditLog(
            case_id=case.id,
            stage=AuditStage.RAG_VERIFICATION,
            actor=f"AI_VERIFIER_{provider.provider_name.upper()}",
            action="CLINICAL_PROTOCOL_VERIFIED",
            details={
                "status": verif_status.value,
                "score": verif_score,
                "protocol_code": proto_code,
                "disclaimer": hybrid.disclaimer,
            },
        )
        db.add(audit_verif)

        # 6. Geocoding & Spatial Resolution (OpenStreetMap Nominatim / GeocodingProvider)
        # Note: If geocoding fails or is ambiguous, the emergency is NEVER rejected.
        # It is marked unverified, surfaces in HumanReview for dispatcher intervention, and logs an audit trail.
        loc_query = result.location
        if not loc_query and case.location and case.location.raw_query and case.location.raw_query != "[Location Not Mentioned]":
            loc_query = case.location.raw_query

        loc, geo_review_trigger = process_case_geocoding(
            case=case,
            location_query=loc_query,
            db=db,
            provider=geocoding_provider,
        )

        # 7. Real Multi-Signal Duplicate Detection Check
        # Uses real semantic cosine similarity, Haversine geographic distance,
        # temporal decay within candidate window, and normalized emergency taxonomy.
        dup_result = run_duplicate_detection(case=case, db=db)
        detected_duplicate = dup_result.duplicate_detected

        # 8. Human Review Routing Logic (Human-in-the-Loop)
        needs_review = (
            hybrid.mandatory_human_review
            or hybrid.final_severity == SeverityLevel.UNKNOWN
            or hybrid.has_conflict
            or result.confidence_score < 0.75
            or result.is_contradictory
            or ("exact location / landmark" in result.missing_information and hybrid.final_severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH))
            or (geo_review_trigger is not None)
            or (loc is not None and not loc.is_verified)
            or dup_result.requires_human_review
        )

        if needs_review:
            case.status = CaseStatus.UNDER_REVIEW
            reasons = list(hybrid.review_triggers)
            if geo_review_trigger:
                reasons.append(geo_review_trigger)
            elif loc and not loc.is_verified:
                reasons.append(f"Location '{loc.raw_query}' unverified ({loc.status.value}) - dispatcher intervention required")
            if result.confidence_score < 0.75:
                reasons.append(f"Confidence {result.confidence_score:.2f} below 0.75 threshold")
            if result.is_contradictory and not any("contradict" in r.lower() for r in reasons):
                reasons.append(f"Contradictory caller report: {result.contradiction_notes or 'inconsistent states'}")
            if result.missing_information:
                reasons.append(f"Missing critical items: {', '.join(result.missing_information)}")
            if dup_result.requires_human_review and dup_result.review_trigger_reason:
                reasons.append(dup_result.review_trigger_reason)
            elif detected_duplicate:
                reasons.append(f"Potential duplicate incident detected (Score: {dup_result.duplicate_score:.2f})")

            review = HumanReview(
                case_id=case.id,
                review_status=ReviewStatus.PENDING,
                trigger_reason="; ".join(reasons) or "Prototype clinical review required",
                original_decision={
                    "severity": hybrid.final_severity.value,
                    "ambulance_requirement": hybrid.final_ambulance.value,
                    "confidence": result.confidence_score,
                    "emergency_type": result.emergency_type,
                    "missing_info": result.missing_information,
                    "ai_suggested_severity": hybrid.ai_suggested_severity.value,
                    "ai_suggested_ambulance": hybrid.ai_suggested_ambulance.value,
                    "deterministic_severity": hybrid.deterministic_severity.value,
                    "deterministic_ambulance": hybrid.deterministic_ambulance.value,
                    "has_conflict": hybrid.has_conflict,
                    "is_duplicate_candidate": detected_duplicate,
                    "duplicate_score": dup_result.duplicate_score,
                    "duplicate_status": dup_result.state.value,
                    "duplicate_matched_case_id": dup_result.best_candidate_id,
                    "disclaimer": hybrid.disclaimer,
                },
            )
            db.add(review)
        else:
            case.status = CaseStatus.TRIAGED

        # 8. Audit Log (Preserving both AI and deterministic results side-by-side)
        audit = AuditLog(
            case_id=case.id,
            stage=AuditStage.AI_EXTRACTION,
            actor=f"AI_ENGINE_{provider.provider_name.upper()}",
            action="EXTRACTION_AND_HYBRID_TRIAGE_COMPLETED",
            details={
                "emergency_type": result.emergency_type,
                "confidence": result.confidence_score,
                "missing_info": result.missing_information,
                "ai_suggestion": {
                    "severity": hybrid.ai_suggested_severity.value,
                    "ambulance": hybrid.ai_suggested_ambulance.value,
                },
                "deterministic_validation": {
                    "severity": hybrid.deterministic_severity.value,
                    "ambulance": hybrid.deterministic_ambulance.value,
                    "has_conflict": hybrid.has_conflict,
                    "conflict_reason": hybrid.conflict_reason,
                },
                "final_recommendation": {
                    "severity": hybrid.final_severity.value,
                    "ambulance_type": hybrid.final_ambulance.value,
                    "routed_status": case.status.value,
                },
                "decision_type": hybrid.decision_type,
                "disclaimer": hybrid.disclaimer,
            },
            latency_ms=latency_ms,
        )
        db.add(audit)

    except Exception as exc:
        # ===================================================================
        # FAIL-SAFE GUARANTEE: NEVER LOSE THE CASE ON LLM FAILURE
        # ===================================================================
        logger.error(
            "LLM extraction failed for case '%s' with %s: %s. Preserving case and routing to human dispatcher.",
            case.id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )

        # 1. Store failed extraction metadata
        extracted = case.extracted_info
        if not extracted:
            extracted = ExtractedInfo(case_id=case.id)
            db.add(extracted)

        extracted.emergency_type = "EXTRACTION_FAILED"
        extracted.extraction_confidence = 0.0
        extracted.raw_llm_output = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "status": "FAILED",
        }

        # 2. Safety escalation: Route to human dispatcher with HIGH priority
        case.status = CaseStatus.UNDER_REVIEW
        case.priority = SeverityLevel.HIGH

        # 3. Create HumanReview task for dispatcher queue
        review = HumanReview(
            case_id=case.id,
            review_status=ReviewStatus.PENDING,
            trigger_reason=f"LLM Extraction Failure ({type(exc).__name__}): {str(exc)}",
            original_decision={
                "status": "FAILED",
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        db.add(review)

        # 4. Immutable Audit Trail
        audit = AuditLog(
            case_id=case.id,
            stage=AuditStage.AI_EXTRACTION,
            actor=f"AI_ENGINE_{provider.provider_name.upper() if provider else 'UNKNOWN'}",
            action="EXTRACTION_FAILED_ROUTED_TO_HUMAN_REVIEW",
            details={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "escalated_priority": SeverityLevel.HIGH.value,
                "routed_status": CaseStatus.UNDER_REVIEW.value,
            },
            latency_ms=int((time.time() - start_time) * 1000),
        )
        db.add(audit)

        # 5. Geocoding Fallback: Mark location as failed (do NOT send raw_text to geocoder!)
        # Only extract AI-identified location text for geocoding. If LLM failed, we have no
        # reliable location to geocode. Mark unverified so dispatcher can intervene.
        try:
            existing_loc = case.location or db.query(Location).filter(Location.case_id == case.id).first()
            if not existing_loc:
                existing_loc = Location(
                    case=case,
                    case_id=case.id,
                    raw_query="[Location extraction failed - LLM unavailable]",
                    status=GeocodingStatus.FAILED,
                    is_verified=False,
                    confidence=0.0,
                    geocoding_provider="none",
                    error_message="LLM extraction failed before location could be identified. Dispatcher must set coordinates manually.",
                )
                case.location = existing_loc
                db.add(existing_loc)
            audit_loc = AuditLog(
                case_id=case.id,
                stage=AuditStage.GEOCODING,
                actor="GEOCODER_FALLBACK",
                action="GEOCODING_SKIPPED_LLM_FAILURE",
                details={"reason": "LLM extraction failed; raw_text NOT sent to geocoder to prevent false geocoding. Dispatcher intervention required."},
            )
            db.add(audit_loc)
        except Exception as geo_exc:
            logger.warning("Location failure marking failed: %s", geo_exc)

    db.commit()
    db.refresh(case)
    return case

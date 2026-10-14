"""System-Level Multi-Signal Weighted Confidence Scoring Engine.

Computes system confidence without blindly trusting LLM self-reports.
Weights:
- Extraction Completeness  = 25% (0.25)
- Rule/LLM Agreement       = 20% (0.20)
- Location Verification    = 20% (0.20)
- Resource Availability    = 15% (0.15)
- Duplicate Certainty      = 10% (0.10)
- LLM Self-Confidence      = 10% (0.10)

Thresholds:
- HIGH   : >= 0.75
- MEDIUM : 0.50 to 0.74
- LOW    : < 0.50  (MANDATORY Human-in-the-Loop Review)
"""
import logging
from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType
from app.models.ambulance import Ambulance, AmbulanceStatus
from app.models.hospital import Hospital
from app.models.location import Location, GeocodingStatus

logger = logging.getLogger(__name__)


class ConfidenceBreakdown(BaseModel):
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: str = Field(..., description="HIGH (>=0.75), MEDIUM (0.50-0.74), LOW (<0.50)")
    requires_human_review: bool
    review_trigger_reason: str = ""
    components: Dict[str, float] = Field(
        ...,
        description="Individual scores for the 6 weighted evaluation dimensions",
    )


def calculate_system_confidence(case: Case, db: Session) -> ConfidenceBreakdown:
    """
    Evaluate multi-signal composite confidence score for an emergency case.
    """
    ext = case.extracted_info
    loc = db.query(Location).filter(Location.case_id == case.id).order_by(Location.created_at.desc()).first() if db else case.location
    decision = case.ai_decisions[-1] if case.ai_decisions else None

    # 1. Extraction Completeness (25%)
    score_extraction = 0.0
    if ext:
        if ext.emergency_type and ext.emergency_type.lower() != "unknown":
            score_extraction += 0.35
        if ext.symptoms and len(ext.symptoms) > 0:
            score_extraction += 0.30
        if ext.extracted_location_text and len(ext.extracted_location_text.strip()) > 3:
            score_extraction += 0.20
        if ext.conscious_status or ext.breathing_status or (ext.patient_count and ext.patient_count > 0):
            score_extraction += 0.15
    score_extraction = min(1.0, score_extraction)

    # 2. Rule / LLM Agreement (20%)
    score_rule_agreement = 1.0
    if decision:
        if decision.has_conflict:
            score_rule_agreement = 0.20
        elif (
            decision.ai_suggested_severity
            and decision.deterministic_severity
            and decision.ai_suggested_severity == decision.deterministic_severity
            and decision.ai_suggested_ambulance == decision.deterministic_ambulance
        ):
            score_rule_agreement = 1.0
        elif (
            decision.ai_suggested_severity == decision.deterministic_severity
            or decision.ai_suggested_ambulance == decision.deterministic_ambulance
        ):
            score_rule_agreement = 0.65
        else:
            score_rule_agreement = 0.35

    # 3. Location Verification (20%)
    score_location = 0.0
    if loc:
        if loc.is_verified and loc.status == GeocodingStatus.SUCCESS:
            score_location = 1.0
        elif loc.status == GeocodingStatus.SUCCESS:
            score_location = 0.75
        elif loc.status == GeocodingStatus.AMBIGUOUS:
            score_location = 0.40
        else:
            score_location = 0.0  # FAILED or missing coordinates

    # 4. Resource Availability (15%)
    score_resources = 0.0
    # Check ambulance availability
    available_amb_count = (
        db.query(Ambulance)
        .filter(Ambulance.status == AmbulanceStatus.AVAILABLE)
        .count()
    )
    # Check active hospitals with beds
    active_hosp_count = (
        db.query(Hospital)
        .filter(Hospital.is_active == True, Hospital.available_beds > 0)
        .count()
    )

    if available_amb_count > 0 and active_hosp_count > 0:
        score_resources = 1.0
    elif available_amb_count > 0 or active_hosp_count > 0:
        score_resources = 0.50
    else:
        score_resources = 0.10

    # 5. Duplicate Certainty (10%)
    score_duplicate = 1.0
    if case.duplicate_associations:
        dup = case.duplicate_associations[0]
        if dup.is_confirmed_duplicate:
            score_duplicate = 0.90
        elif dup.overall_confidence > 0.80:
            score_duplicate = 0.50  # Unconfirmed high-probability duplicate flags caution
        else:
            score_duplicate = 0.70
    elif case.duplicate_of:
        score_duplicate = 0.85

    # 6. LLM Self-Confidence (10%)
    score_llm = 0.50
    if ext and ext.extraction_confidence is not None:
        score_llm = max(0.0, min(1.0, float(ext.extraction_confidence)))
    elif decision and decision.confidence_score is not None:
        score_llm = max(0.0, min(1.0, float(decision.confidence_score)))

    # Weighted Sum Calculation
    overall = (
        0.25 * score_extraction
        + 0.20 * score_rule_agreement
        + 0.20 * score_location
        + 0.15 * score_resources
        + 0.10 * score_duplicate
        + 0.10 * score_llm
    )
    overall = round(max(0.0, min(1.0, overall)), 4)

    # Classify Confidence Level
    if overall >= 0.75:
        level = "HIGH"
        requires_review = False
        reason = ""
    elif overall >= 0.50:
        level = "MEDIUM"
        requires_review = False
        reason = ""
    else:
        level = "LOW"
        requires_review = True
        triggers = []
        if score_extraction < 0.60:
            triggers.append(f"Incomplete extraction ({score_extraction:.2f})")
        if score_location < 0.50:
            triggers.append(f"Unverified location ({score_location:.2f})")
        if score_rule_agreement < 0.50:
            triggers.append("Rule/AI clinical contradiction")
        if score_resources < 0.50:
            triggers.append("Resource scarcity")
        reason = f"Low system confidence ({overall:.2f}): " + (", ".join(triggers) or "Multi-signal threshold breach")

    components = {
        "extraction_completeness": round(score_extraction, 4),
        "rule_llm_agreement": round(score_rule_agreement, 4),
        "location_verification": round(score_location, 4),
        "resource_availability": round(score_resources, 4),
        "duplicate_certainty": round(score_duplicate, 4),
        "llm_confidence": round(score_llm, 4),
    }

    return ConfidenceBreakdown(
        overall_confidence=overall,
        confidence_level=level,
        requires_human_review=requires_review,
        review_trigger_reason=reason,
        components=components,
    )

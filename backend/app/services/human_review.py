"""Human-in-the-Loop Dispatcher Review Workflow Service.

Guarantees:
- Never overwrites the original AI decision.
- Stores original AI decision, human decision, reviewer ID, timestamp, and notes side-by-side.
- Supports actions: APPROVE, MODIFY, REJECT, CONFIRM_DUPLICATE, REJECT_DUPLICATE.
- Immutably records audit history at AuditStage.HUMAN_REVIEW.
"""
from datetime import datetime, timezone
import logging
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType
from app.models.human_review import HumanReview, ReviewStatus
from app.models.audit import AuditLog, AuditStage
from app.models.duplicate import DuplicateRelationship
from app.models.location import Location, GeocodingStatus

logger = logging.getLogger(__name__)


def submit_human_review(
    case_id: str,
    action: str,  # "APPROVE", "MODIFY", "REJECT", "CONFIRM_DUPLICATE", "REJECT_DUPLICATE"
    db: Session,
    dispatcher_id: Optional[str] = "dispatcher_1",
    modified_severity: Optional[SeverityLevel] = None,
    modified_ambulance: Optional[AmbulanceType] = None,
    modified_location: Optional[str] = None,
    dispatcher_notes: Optional[str] = None,
    confirm_duplicate: Optional[bool] = None,
) -> Tuple[Case, HumanReview]:
    """
    Process dispatcher intervention without overwriting the original AI decision.
    """
    case: Optional[Case] = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Emergency case '{case_id}' does not exist.")

    # Retrieve or create HumanReview record
    review = (
        db.query(HumanReview)
        .filter(HumanReview.case_id == case.id)
        .order_by(HumanReview.created_at.desc())
        .first()
    )
    if not review:
        review = HumanReview(
            case_id=case.id,
            review_status=ReviewStatus.PENDING,
            trigger_reason="Dispatcher manual intervention",
        )
        db.add(review)

    # Capture snapshot of original AI decision if not already present
    if not review.original_decision:
        latest_ai = case.ai_decisions[-1] if case.ai_decisions else None
        review.original_decision = {
            "severity": latest_ai.severity_assessment.value if latest_ai else case.priority.value,
            "ambulance_type": latest_ai.recommended_ambulance_type.value if latest_ai else None,
            "confidence_score": latest_ai.confidence_score if latest_ai else 0.0,
            "clinical_rationale": latest_ai.clinical_rationale if latest_ai else "",
            "raw_text": case.raw_text,
        }

    now = datetime.now(timezone.utc)
    action_upper = action.upper()
    final_payload: Dict[str, Any] = {
        "action": action_upper,
        "dispatcher_id": dispatcher_id,
        "reviewed_at": now.isoformat(),
        "notes": dispatcher_notes,
    }

    # Execute dispatcher action
    if action_upper == "APPROVE":
        review.review_status = ReviewStatus.APPROVED
        final_payload["status"] = "AI_DECISION_APPROVED"
        final_payload["final_severity"] = case.priority.value
        if case.status == CaseStatus.UNDER_REVIEW:
            case.status = CaseStatus.TRIAGED

    elif action_upper == "MODIFY":
        review.review_status = ReviewStatus.OVERRIDDEN
        if modified_severity:
            case.priority = modified_severity
            final_payload["modified_severity"] = modified_severity.value
        if modified_ambulance:
            final_payload["modified_ambulance"] = modified_ambulance.value
        if modified_location:
            final_payload["modified_location"] = modified_location
            if case.location:
                case.location.raw_query = modified_location
                case.location.is_verified = True
                case.location.status = GeocodingStatus.SUCCESS

        if case.status == CaseStatus.UNDER_REVIEW:
            case.status = CaseStatus.TRIAGED

    elif action_upper == "REJECT":
        review.review_status = ReviewStatus.OVERRIDDEN
        final_payload["status"] = "AI_DECISION_REJECTED"
        case.status = CaseStatus.CANCELLED

    elif action_upper == "CONFIRM_DUPLICATE":
        review.review_status = ReviewStatus.APPROVED
        final_payload["status"] = "CONFIRMED_DUPLICATE"
        case.status = CaseStatus.DUPLICATE
        # Mark duplicate relationships confirmed
        for dup in case.duplicate_associations:
            dup.is_confirmed_duplicate = True
        for dup in case.duplicate_of:
            dup.is_confirmed_duplicate = True

    elif action_upper == "REJECT_DUPLICATE":
        review.review_status = ReviewStatus.OVERRIDDEN
        final_payload["status"] = "DUPLICATE_REJECTED_INDEPENDENT_INCIDENT"
        for dup in case.duplicate_associations:
            dup.is_confirmed_duplicate = False
        for dup in case.duplicate_of:
            dup.is_confirmed_duplicate = False
        if case.status in (CaseStatus.UNDER_REVIEW, CaseStatus.DUPLICATE):
            case.status = CaseStatus.TRIAGED

    else:
        raise ValueError(f"Unknown review action '{action}'.")

    # Update review record
    review.dispatcher_id = dispatcher_id
    review.final_decision = final_payload
    review.dispatcher_notes = dispatcher_notes
    review.reviewed_at = now

    # Immutable Audit Log
    audit = AuditLog(
        case_id=case.id,
        stage=AuditStage.HUMAN_REVIEW,
        actor=f"DISPATCHER_{dispatcher_id or 'UNKNOWN'}",
        action=f"HUMAN_REVIEW_{action_upper}",
        details={
            "action": action_upper,
            "original_decision": review.original_decision,
            "final_decision": final_payload,
            "dispatcher_notes": dispatcher_notes,
            "case_status_after": case.status.value,
        },
    )
    db.add(audit)

    db.commit()
    db.refresh(review)
    db.refresh(case)
    return case, review

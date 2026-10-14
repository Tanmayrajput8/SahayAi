"""Endpoints for Confidence Scoring and Human-in-the-Loop Dispatcher Review."""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.case import Case, CaseStatus, SeverityLevel, AmbulanceType
from app.models.human_review import HumanReview
from app.services.confidence_scoring import calculate_system_confidence, ConfidenceBreakdown
from app.services.human_review import submit_human_review

logger = logging.getLogger(__name__)

router = APIRouter()


class HumanReviewRequest(BaseModel):
    action: str = Field(..., description="Action: 'APPROVE', 'MODIFY', 'REJECT', 'CONFIRM_DUPLICATE', 'REJECT_DUPLICATE'")
    modified_severity: Optional[SeverityLevel] = Field(default=None, description="Updated clinical priority")
    modified_ambulance: Optional[AmbulanceType] = Field(default=None, description="Updated ambulance tier (ALS / BLS)")
    modified_location: Optional[str] = Field(default=None, description="Corrected landmark/location text")
    dispatcher_id: Optional[str] = Field(default="dispatcher_1", description="ID or callsign of reviewer")
    dispatcher_notes: Optional[str] = Field(default=None, description="Clinical/operational justification")
    confirm_duplicate: Optional[bool] = Field(default=None)


class ReviewQueueItem(BaseModel):
    case_id: str
    status: CaseStatus
    priority: SeverityLevel
    raw_text: str
    emergency_type: Optional[str] = None
    confidence_score: float = 0.0
    confidence_level: str = "LOW"
    trigger_reason: str
    created_at: str
    duplicate_candidate: bool = False


@router.get(
    "/queue",
    response_model=List[ReviewQueueItem],
    summary="List Human-in-the-Loop Review Queue",
    description="Retrieve all emergency cases currently requiring human dispatcher intervention or confirmation.",
)
def get_review_queue(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> List[ReviewQueueItem]:
    cases = (
        db.query(Case)
        .filter(Case.status == CaseStatus.UNDER_REVIEW)
        .order_by(Case.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items: List[ReviewQueueItem] = []
    for c in cases:
        review = c.human_reviews[-1] if c.human_reviews else None
        ext = c.extracted_info
        conf_breakdown = calculate_system_confidence(c, db)

        items.append(
            ReviewQueueItem(
                case_id=c.id,
                status=c.status,
                priority=c.priority,
                raw_text=c.raw_text,
                emergency_type=ext.emergency_type if ext else None,
                confidence_score=conf_breakdown.overall_confidence,
                confidence_level=conf_breakdown.confidence_level,
                trigger_reason=review.trigger_reason if review else "System flagged for review",
                created_at=c.created_at.isoformat(),
                duplicate_candidate=bool(c.duplicate_associations or c.duplicate_of),
            )
        )
    return items


@router.get(
    "/{case_id}/confidence",
    response_model=ConfidenceBreakdown,
    summary="Get Multi-Signal Confidence Breakdown",
    description="Calculates composite confidence from 6 weighted signals (Extraction, Rule Agreement, Location, Resources, Duplicate, LLM).",
)
def get_case_confidence(case_id: str, db: Session = Depends(get_db)) -> ConfidenceBreakdown:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Case '{case_id}' not found."},
        )
    return calculate_system_confidence(case, db)


@router.post(
    "/{case_id}/submit",
    summary="Submit Human Dispatcher Review Decision",
    description="Approve, modify, or reject AI decisions while strictly preserving the original AI recommendation.",
)
def submit_case_review(
    case_id: str,
    payload: HumanReviewRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    try:
        updated_case, review = submit_human_review(
            case_id=case_id,
            action=payload.action,
            db=db,
            dispatcher_id=payload.dispatcher_id,
            modified_severity=payload.modified_severity,
            modified_ambulance=payload.modified_ambulance,
            modified_location=payload.modified_location,
            dispatcher_notes=payload.dispatcher_notes,
            confirm_duplicate=payload.confirm_duplicate,
        )
        return {
            "case_id": updated_case.id,
            "case_status": updated_case.status.value,
            "priority": updated_case.priority.value,
            "review_status": review.review_status.value,
            "original_decision": review.original_decision,
            "final_decision": review.final_decision,
            "dispatcher_notes": review.dispatcher_notes,
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_action", "message": str(exc)},
        )

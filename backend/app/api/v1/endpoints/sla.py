"""Endpoints for SLA Monitoring, Warning Generation, and Escalations."""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.sla import SLATracking
from app.models.escalation import EscalationEvent
from app.models.case import Case, CaseStatus
from app.services.sla_monitoring import (
    check_case_sla,
    check_all_active_slas,
    resolve_escalation,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ResolveEscalationRequest(BaseModel):
    resolution_notes: str = Field(..., description="Action taken by supervisor")
    supervisor_id: Optional[str] = Field(default="supervisor_1")


class EscalationResponse(BaseModel):
    id: str
    case_id: str
    escalation_level: str
    triggered_by: str
    reason: str
    resolved_at: Optional[str] = None
    resolution_notes: Optional[str] = None
    created_at: str


class SLAStatusItem(BaseModel):
    case_id: str
    priority: str
    case_status: str
    target_seconds: int
    elapsed_seconds: int
    is_warning: bool
    is_breached: bool
    breach_duration_seconds: int


@router.get(
    "/status",
    response_model=List[SLAStatusItem],
    summary="Get SLA Timers for Active Cases",
    description="Inspect elapsed time against prototype thresholds (Critical 8m, High 12m, Moderate 20m, Low 30m).",
)
def get_sla_status(db: Session = Depends(get_db)) -> List[SLAStatusItem]:
    active_slas = (
        db.query(SLATracking)
        .join(Case, Case.id == SLATracking.case_id)
        .filter(Case.status.in_([CaseStatus.PENDING, CaseStatus.TRIAGED, CaseStatus.UNDER_REVIEW]))
        .all()
    )

    items: List[SLAStatusItem] = []
    for s in active_slas:
        items.append(
            SLAStatusItem(
                case_id=s.case_id,
                priority=s.severity_level.value,
                case_status=s.case.status.value,
                target_seconds=s.target_seconds,
                elapsed_seconds=s.elapsed_seconds,
                is_warning=s.is_warning,
                is_breached=s.is_breached,
                breach_duration_seconds=s.breach_duration_seconds,
            )
        )
    return items


@router.post(
    "/check",
    summary="Trigger SLA Check Cycle",
    description="Periodic inspector running across active cases to update warning and breach flags.",
)
def trigger_sla_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return check_all_active_slas(db)


@router.get(
    "/escalations",
    response_model=List[EscalationResponse],
    summary="List Escalations",
    description="Retrieve all supervisor escalation events, filterable by unresolved status.",
)
def list_escalations(
    unresolved_only: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> List[EscalationResponse]:
    query = db.query(EscalationEvent)
    if unresolved_only:
        query = query.filter(EscalationEvent.resolved_at.is_(None))
    events = query.order_by(EscalationEvent.created_at.desc()).all()

    return [
        EscalationResponse(
            id=e.id,
            case_id=e.case_id,
            escalation_level=e.escalation_level.value,
            triggered_by=e.triggered_by.value,
            reason=e.reason,
            resolved_at=e.resolved_at.isoformat() if e.resolved_at else None,
            resolution_notes=e.resolution_notes,
            created_at=e.created_at.isoformat(),
        )
        for e in events
    ]


@router.post(
    "/escalations/{escalation_id}/resolve",
    response_model=EscalationResponse,
    summary="Resolve Escalation Alert",
    description="Marks an active supervisor escalation alert as resolved with recorded notes.",
)
def resolve_escalation_endpoint(
    escalation_id: str,
    payload: ResolveEscalationRequest,
    db: Session = Depends(get_db),
) -> EscalationResponse:
    try:
        esc = resolve_escalation(
            escalation_id=escalation_id,
            resolution_notes=payload.resolution_notes,
            supervisor_id=payload.supervisor_id or "supervisor_1",
            db=db,
        )
        return EscalationResponse(
            id=esc.id,
            case_id=esc.case_id,
            escalation_level=esc.escalation_level.value,
            triggered_by=esc.triggered_by.value,
            reason=esc.reason,
            resolved_at=esc.resolved_at.isoformat() if esc.resolved_at else None,
            resolution_notes=esc.resolution_notes,
            created_at=esc.created_at.isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": str(exc)},
        )

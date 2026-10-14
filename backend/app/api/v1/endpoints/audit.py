"""Endpoints for Comprehensive Audit Logging and Provenance Tracking."""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit import AuditLog, AuditStage

logger = logging.getLogger(__name__)

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: str
    case_id: str
    stage: str
    actor: str
    action: str
    details: Dict[str, Any]
    latency_ms: int
    created_at: str


@router.get(
    "/logs",
    response_model=List[AuditLogResponse],
    summary="List Audit Event Logs",
    description="Retrieve chronological audit trails, filterable by case ID, pipeline stage, actor, or action.",
)
def list_audit_logs(
    case_id: Optional[str] = Query(default=None),
    stage: Optional[AuditStage] = Query(default=None),
    action: Optional[str] = Query(default=None),
    actor: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[AuditLogResponse]:
    query = db.query(AuditLog)
    if case_id:
        query = query.filter(AuditLog.case_id == case_id)
    if stage:
        query = query.filter(AuditLog.stage == stage)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if actor:
        query = query.filter(AuditLog.actor.ilike(f"%{actor}%"))

    logs = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

    return [
        AuditLogResponse(
            id=log.id,
            case_id=log.case_id,
            stage=log.stage.value,
            actor=log.actor,
            action=log.action,
            details=log.details or {},
            latency_ms=log.latency_ms or 0,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.get(
    "/cases/{case_id}/timeline",
    response_model=List[AuditLogResponse],
    summary="Get Chronological Case Timeline",
    description="Returns full audit event history for a specific case from intake to dispatch/resolution.",
)
def get_case_timeline(
    case_id: str,
    db: Session = Depends(get_db),
) -> List[AuditLogResponse]:
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    return [
        AuditLogResponse(
            id=log.id,
            case_id=log.case_id,
            stage=log.stage.value,
            actor=log.actor,
            action=log.action,
            details=log.details or {},
            latency_ms=log.latency_ms or 0,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]

"""SLA Monitoring and Idempotent Escalation Service.

Prototype Thresholds (NOT medical/legal standards):
- Critical : 8 minutes  (480s) -> Warning at ~5.6 minutes (336s)
- High     : 12 minutes (720s) -> Warning at ~8.4 minutes (504s)
- Moderate : 20 minutes (1200s)-> Warning at ~14 minutes  (840s)
- Low      : 30 minutes (1800s)-> Warning at ~21 minutes  (1260s)

Guarantees:
- Warns at ~70% of SLA duration.
- Escalates at 100% of SLA duration (breach).
- Idempotent: Never creates duplicate escalation events for the same breach state.
"""
from datetime import datetime, timezone
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.models.case import Case, CaseStatus, SeverityLevel
from app.models.sla import SLATracking
from app.models.escalation import EscalationEvent, EscalationLevel, EscalationTrigger
from app.models.audit import AuditLog, AuditStage
from app.models.ambulance import Ambulance, AmbulanceStatus

logger = logging.getLogger(__name__)

# Prototype SLA durations in seconds
SLA_TARGET_SECONDS: Dict[SeverityLevel, int] = {
    SeverityLevel.CRITICAL: 480,   # 8 minutes
    SeverityLevel.HIGH: 720,       # 12 minutes
    SeverityLevel.MODERATE: 1200,  # 20 minutes
    SeverityLevel.LOW: 1800,       # 30 minutes
    SeverityLevel.UNKNOWN: 1200,   # 20 minutes default
}

WARNING_RATIO: float = 0.70  # Warning triggered at 70% of target duration


def get_target_seconds_for_severity(priority: SeverityLevel) -> int:
    return SLA_TARGET_SECONDS.get(priority, 1200)


def get_or_create_sla_tracking(case: Case, db: Session) -> SLATracking:
    """Ensure an SLATracking entity exists for the case."""
    sla = case.sla_tracking
    if not sla:
        target_sec = get_target_seconds_for_severity(case.priority)
        sla = SLATracking(
            case_id=case.id,
            severity_level=case.priority,
            target_seconds=target_sec,
            started_at=case.created_at or datetime.now(timezone.utc),
            elapsed_seconds=0,
            is_breached=False,
            is_warning=False,
        )
        db.add(sla)
        db.commit()
        db.refresh(sla)
    return sla


def check_case_sla(
    case_id: str,
    db: Session,
    simulated_now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Inspect a single case's SLA timer, update breach/warning status, and trigger escalation if breached.
    """
    case: Optional[Case] = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise ValueError(f"Case with ID '{case_id}' does not exist.")

    sla = get_or_create_sla_tracking(case, db)
    now = simulated_now or datetime.now(timezone.utc)
    now_dt = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
    started_at_dt = sla.started_at.astimezone(timezone.utc).replace(tzinfo=None) if (sla.started_at and sla.started_at.tzinfo) else sla.started_at

    # If case already dispatched or resolved, stop timer
    if case.status in (CaseStatus.DISPATCHED, CaseStatus.RESOLVED, CaseStatus.CANCELLED):
        if not sla.completed_at:
            sla.completed_at = now
            sla.elapsed_seconds = max(0, int((now_dt - started_at_dt).total_seconds())) if started_at_dt else 0
            db.commit()
        return {
            "case_id": case.id,
            "status": "COMPLETED",
            "elapsed_seconds": sla.elapsed_seconds,
            "target_seconds": sla.target_seconds,
            "is_breached": sla.is_breached,
        }

    # Calculate active elapsed seconds
    elapsed = max(0, int((now_dt - started_at_dt).total_seconds())) if started_at_dt else 0
    sla.elapsed_seconds = elapsed

    warning_threshold = int(sla.target_seconds * WARNING_RATIO)
    warning_triggered = False
    breach_triggered = False
    escalation_created = False

    # 1. Check Breach (>= 100% of target)
    if elapsed >= sla.target_seconds:
        sla.breach_duration_seconds = elapsed - sla.target_seconds
        if not sla.is_breached:
            sla.is_breached = True
            sla.breached_at = now
            breach_triggered = True

            # Audit Log for Breach
            audit_breach = AuditLog(
                case_id=case.id,
                stage=AuditStage.SLA_ESCALATION,
                actor="SLA_MONITOR",
                action="SLA_BREACH",
                details={
                    "severity": case.priority.value,
                    "target_seconds": sla.target_seconds,
                    "elapsed_seconds": elapsed,
                    "breach_duration_seconds": sla.breach_duration_seconds,
                },
            )
            db.add(audit_breach)

            # Idempotent Escalation: Check if active escalation already exists
            existing_escalation = (
                db.query(EscalationEvent)
                .filter(
                    EscalationEvent.case_id == case.id,
                    EscalationEvent.triggered_by == EscalationTrigger.SYSTEM_SLA,
                    EscalationEvent.resolved_at.is_(None),
                )
                .first()
            )

            if not existing_escalation:
                # Suggest backup resource
                backup_amb = (
                    db.query(Ambulance)
                    .filter(Ambulance.status == AmbulanceStatus.AVAILABLE)
                    .first()
                )
                backup_note = f" Backup unit available: {backup_amb.vehicle_number}." if backup_amb else " WARNING: No idle fleet units."

                escalation = EscalationEvent(
                    case_id=case.id,
                    escalation_level=EscalationLevel.SUPERVISOR_ALERT,
                    triggered_by=EscalationTrigger.SYSTEM_SLA,
                    reason=(
                        f"PROTOTYPE SLA BREACH: Case priority '{case.priority.value}' elapsed {elapsed // 60}m "
                        f"(Target: {sla.target_seconds // 60}m). Supervisor intervention required.{backup_note}"
                    ),
                )
                db.add(escalation)
                escalation_created = True

                audit_esc = AuditLog(
                    case_id=case.id,
                    stage=AuditStage.SLA_ESCALATION,
                    actor="SLA_MONITOR",
                    action="ESCALATION_CREATED",
                    details={
                        "escalation_level": EscalationLevel.SUPERVISOR_ALERT.value,
                        "reason": escalation.reason,
                    },
                )
                db.add(audit_esc)

    # 2. Check Warning (>= 70% of target and < 100%)
    elif elapsed >= warning_threshold:
        if not sla.is_warning and not sla.is_breached:
            sla.is_warning = True
            sla.warning_triggered_at = now
            warning_triggered = True

            audit_warn = AuditLog(
                case_id=case.id,
                stage=AuditStage.SLA_ESCALATION,
                actor="SLA_MONITOR",
                action="SLA_WARNING",
                details={
                    "severity": case.priority.value,
                    "target_seconds": sla.target_seconds,
                    "elapsed_seconds": elapsed,
                    "threshold_percent": 70,
                },
            )
            db.add(audit_warn)

    if breach_triggered or warning_triggered or escalation_created:
        db.commit()
        db.refresh(sla)

    return {
        "case_id": case.id,
        "priority": case.priority.value,
        "elapsed_seconds": elapsed,
        "target_seconds": sla.target_seconds,
        "warning_threshold_seconds": warning_threshold,
        "is_warning": sla.is_warning,
        "is_breached": sla.is_breached,
        "warning_triggered": warning_triggered,
        "breach_triggered": breach_triggered,
        "escalation_created": escalation_created,
    }


def check_all_active_slas(db: Session, simulated_now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Inspect all pending/triaged/under-review cases and update SLA timers.
    """
    active_cases = (
        db.query(Case)
        .filter(Case.status.in_([CaseStatus.PENDING, CaseStatus.TRIAGED, CaseStatus.UNDER_REVIEW]))
        .all()
    )

    checked = 0
    warnings = 0
    breaches = 0
    escalations = 0

    for c in active_cases:
        res = check_case_sla(c.id, db, simulated_now=simulated_now)
        checked += 1
        if res.get("warning_triggered"):
            warnings += 1
        if res.get("breach_triggered"):
            breaches += 1
        if res.get("escalation_created"):
            escalations += 1

    return {
        "active_cases_checked": checked,
        "new_warnings": warnings,
        "new_breaches": breaches,
        "new_escalations": escalations,
    }


def resolve_escalation(
    escalation_id: str,
    resolution_notes: str,
    db: Session,
    supervisor_id: str = "supervisor_1",
) -> EscalationEvent:
    """Resolve an escalation alert."""
    esc: Optional[EscalationEvent] = db.query(EscalationEvent).filter(EscalationEvent.id == escalation_id).first()
    if not esc:
        raise ValueError(f"Escalation event with ID '{escalation_id}' does not exist.")

    now = datetime.now(timezone.utc)
    esc.resolved_at = now
    esc.resolution_notes = f"Resolved by {supervisor_id}: {resolution_notes}"

    audit = AuditLog(
        case_id=esc.case_id,
        stage=AuditStage.SLA_ESCALATION,
        actor=f"SUPERVISOR_{supervisor_id}",
        action="ESCALATION_RESOLVED",
        details={
            "escalation_id": esc.id,
            "resolution_notes": esc.resolution_notes,
            "resolved_at": now.isoformat(),
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(esc)
    return esc

"""Unit and API integration tests for SLA Monitoring, Warning Thresholds, and Idempotent Escalations."""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.case import Case, CaseStatus, SeverityLevel, InputModality
from app.models.sla import SLATracking
from app.models.escalation import EscalationEvent, EscalationLevel, EscalationTrigger
from app.services.sla_monitoring import (
    get_target_seconds_for_severity,
    get_or_create_sla_tracking,
    check_case_sla,
    resolve_escalation,
)


def test_sla_target_durations():
    """Verify prototype SLA durations per severity."""
    assert get_target_seconds_for_severity(SeverityLevel.CRITICAL) == 480   # 8 minutes
    assert get_target_seconds_for_severity(SeverityLevel.HIGH) == 720       # 12 minutes
    assert get_target_seconds_for_severity(SeverityLevel.MODERATE) == 1200  # 20 minutes
    assert get_target_seconds_for_severity(SeverityLevel.LOW) == 1800       # 30 minutes


def test_sla_warning_at_70_percent(client: TestClient):
    """Test warning triggered when elapsed time exceeds 70% threshold."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        case = Case(
            caller_phone="9876543210",
            raw_text="Fall from ladder in Deccan",
            modality=InputModality.TEXT.value,
            status=CaseStatus.PENDING,
            priority=SeverityLevel.CRITICAL,
        )
        db.add(case)
        db.commit()

        start_time = datetime.now(timezone.utc) - timedelta(seconds=350) # 350s > 480 * 0.70 (336s)
        sla = SLATracking(
            case_id=case.id,
            severity_level=case.priority,
            target_seconds=480,
            started_at=start_time,
            elapsed_seconds=0,
            is_breached=False,
            is_warning=False,
        )
        db.add(sla)
        db.commit()

        res = check_case_sla(case.id, db)
        assert res["is_warning"] is True
        assert res["is_breached"] is False
    finally:
        db.close()


def test_sla_breach_and_idempotent_escalation(client: TestClient):
    """Test SLA breach at 100% and guarantee that repeated checks do not duplicate escalations."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        case = Case(
            caller_phone="9876543211",
            raw_text="Breathing difficulty in Camp",
            modality=InputModality.TEXT.value,
            status=CaseStatus.PENDING,
            priority=SeverityLevel.CRITICAL,
        )
        db.add(case)
        db.commit()

        # Start 500 seconds ago (> 480s breach)
        start_time = datetime.now(timezone.utc) - timedelta(seconds=500)
        sla = SLATracking(
            case_id=case.id,
            severity_level=case.priority,
            target_seconds=480,
            started_at=start_time,
            elapsed_seconds=0,
            is_breached=False,
            is_warning=False,
        )
        db.add(sla)
        db.commit()

        # First check -> should trigger breach and create 1 escalation
        res1 = check_case_sla(case.id, db)
        assert res1["is_breached"] is True
        assert res1["breach_triggered"] is True
        assert res1["escalation_created"] is True

        escalations_count_1 = (
            db.query(EscalationEvent)
            .filter(EscalationEvent.case_id == case.id)
            .count()
        )
        assert escalations_count_1 == 1

        # Second check -> MUST BE IDEMPOTENT (no new escalation created)
        res2 = check_case_sla(case.id, db)
        assert res2["is_breached"] is True
        assert res2["breach_triggered"] is False
        assert res2["escalation_created"] is False

        escalations_count_2 = (
            db.query(EscalationEvent)
            .filter(EscalationEvent.case_id == case.id)
            .count()
        )
        assert escalations_count_2 == 1
    finally:
        db.close()


def test_api_sla_check_and_escalations(client: TestClient):
    """Test POST /api/v1/sla/check and GET /api/v1/sla/escalations."""
    # Run cycle
    cycle_resp = client.post("/api/v1/sla/check")
    assert cycle_resp.status_code == 200
    assert "active_cases_checked" in cycle_resp.json()

    # Query escalations
    esc_resp = client.get("/api/v1/sla/escalations")
    assert esc_resp.status_code == 200
    assert isinstance(esc_resp.json(), list)

    # Status list
    stat_resp = client.get("/api/v1/sla/status")
    assert stat_resp.status_code == 200
    assert isinstance(stat_resp.json(), list)

"""Unit and API integration tests for Fairness Evaluation and Comprehensive Audit Logging."""
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient

from app.models.case import Case, CaseStatus, SeverityLevel, InputModality
from app.models.audit import AuditLog, AuditStage
from app.services.fairness_eval import run_fairness_evaluation


def test_fairness_evaluation_benchmark_execution():
    """Verify fairness evaluation executes across all 4 multilingual language groups."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        report = run_fairness_evaluation(db=db)
        assert "overall_metrics" in report
        assert "language_breakdown" in report

        breakdown = report["language_breakdown"]
        # Must include all 4 language groups
        for lang in ["English", "Hindi", "Marathi", "Code-Mixed"]:
            assert lang in breakdown
            assert breakdown[lang]["total_cases"] > 0
            assert "severity_accuracy" in breakdown[lang]
            assert "ambulance_accuracy" in breakdown[lang]

        # Must report actual disparity calculation
        assert "max_severity_disparity" in report
    finally:
        db.close()


def test_api_fairness_benchmark_endpoint(client: TestClient):
    """Test GET /api/v1/fairness/benchmark endpoint."""
    resp = client.get("/api/v1/fairness/benchmark")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_metrics" in data
    assert "language_breakdown" in data


def test_audit_logs_recording_and_filtering(client: TestClient):
    """Test audit log creation and API retrieval with filters."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        case = Case(
            caller_phone="9988770011",
            raw_text="Audit test emergency case",
            modality=InputModality.TEXT.value,
            status=CaseStatus.PENDING,
            priority=SeverityLevel.HIGH,
        )
        db.add(case)
        db.commit()

        log1 = AuditLog(
            case_id=case.id,
            stage=AuditStage.INTAKE,
            actor="SYSTEM_API",
            action="CASE_CREATED",
            details={"source": "api_test"},
        )
        log2 = AuditLog(
            case_id=case.id,
            stage=AuditStage.SEVERITY_RECOMMENDATION,
            actor="MOCK_MODEL",
            action="SEVERITY_CLASSIFIED",
            details={"priority": "HIGH", "ambulance": "ALS"},
        )
        db.add_all([log1, log2])
        db.commit()

        # Query timeline
        timeline_resp = client.get(f"/api/v1/audit/cases/{case.id}/timeline")
        assert timeline_resp.status_code == 200
        events = timeline_resp.json()
        assert len(events) >= 2
        actions = [e["action"] for e in events]
        assert "CASE_CREATED" in actions
        assert "SEVERITY_CLASSIFIED" in actions

        # Filter by stage
        filter_resp = client.get(f"/api/v1/audit/logs?stage={AuditStage.SEVERITY_RECOMMENDATION.value}")
        assert filter_resp.status_code == 200
        logs = filter_resp.json()
        assert all(l["stage"] == AuditStage.SEVERITY_RECOMMENDATION.value for l in logs)
    finally:
        db.close()


def test_audit_logs_security_no_secret_leakage(client: TestClient):
    """Verify that audit logs never store or expose API keys, passwords, or secrets."""
    resp = client.get("/api/v1/audit/logs?limit=50")
    assert resp.status_code == 200
    logs = resp.json()

    forbidden_keys = ["api_key", "secret", "password", "jwt_secret", "token", "groq_api_key", "grok_api_key"]
    for log_item in logs:
        details_str = str(log_item.get("details", {})).lower()
        for key in forbidden_keys:
            assert f"'{key}'" not in details_str, f"Sensitive key {key} leaked in audit details!"

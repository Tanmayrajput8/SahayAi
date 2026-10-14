from app.db.session import SessionLocal
from app.db.seed import seed_database
from app.models import (
    Incident,
    IncidentStatus,
    SeverityLevel,
    AmbulanceType,
    Hospital,
    Ambulance,
    AuditLog,
    AuditStage,
    EmergencyProtocol,
)


def test_seed_data_presence():
    """Verify that simulated Pune hospitals, ambulances, and protocols are populated."""
    with SessionLocal() as db:
        seed_database(db)

        hospitals = db.query(Hospital).all()
        assert len(hospitals) >= 8
        hospital_names = [h.name for h in hospitals]
        assert "Sassoon General Hospital" in hospital_names
        assert "Deenanath Mangeshkar Hospital" in hospital_names

        # Verify trauma and cardiac flags
        sassoon = db.query(Hospital).filter(Hospital.name == "Sassoon General Hospital").first()
        assert sassoon.has_trauma_center is True
        assert sassoon.has_burn_unit is True

        ambulances = db.query(Ambulance).all()
        assert len(ambulances) >= 10
        als_count = sum(1 for a in ambulances if a.ambulance_type == AmbulanceType.ALS)
        bls_count = sum(1 for a in ambulances if a.ambulance_type == AmbulanceType.BLS)
        assert als_count > 0
        assert bls_count > 0

        protocols = db.query(EmergencyProtocol).all()
        assert len(protocols) >= 6
        codes = [p.protocol_code for p in protocols]
        assert "CARD-01" in codes
        assert "TRAUMA-01" in codes


def test_incident_creation_and_relations():
    """Verify creating a Case (Incident alias) with AuditLog relation using normalized schema."""
    with SessionLocal() as db:
        seed_database(db)

        incident = Incident(
            raw_text="Major heart attack at Kothrud, severe chest pain radiating to arm",
            language="english",
            priority=SeverityLevel.CRITICAL,
            status=IncidentStatus.TRIAGED,
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)

        # Attach Audit Log using case_id (normalized column)
        audit = AuditLog(
            case_id=incident.id,
            stage=AuditStage.DISPATCH,
            actor="AI_DISPATCH_ENGINE",
            action="ALS_AMBULANCE_DISPATCHED",
            details={"emergency_type": "CARDIAC", "severity": "CRITICAL"},
            latency_ms=180,
        )
        db.add(audit)
        db.commit()

        # Query back and verify relations
        queried = db.query(Incident).filter(Incident.id == incident.id).first()
        assert queried is not None
        assert queried.language == "english"
        assert queried.priority == SeverityLevel.CRITICAL
        assert len(queried.audit_logs) == 1
        assert queried.audit_logs[0].stage == AuditStage.DISPATCH
        assert queried.audit_logs[0].actor == "AI_DISPATCH_ENGINE"

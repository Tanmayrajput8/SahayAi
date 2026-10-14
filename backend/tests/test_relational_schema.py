from datetime import datetime, timezone, timedelta
from sqlalchemy import inspect
from app.db.session import SessionLocal, engine
from app.models import (
    User,
    UserRole,
    Case,
    CaseStatus,
    SeverityLevel,
    AmbulanceType,
    ExtractedInfo,
    Location,
    Ambulance,
    AmbulanceStatus,
    Hospital,
    ResourceMatch,
    DuplicateRelationship,
    AIDecision,
    VerificationResult,
    VerificationStatus,
    HumanReview,
    ReviewStatus,
    SLATracking,
    EscalationEvent,
    EscalationLevel,
    EscalationTrigger,
    AuditLog,
    AuditStage,
    FairnessRecord,
    EmergencyProtocol,
)
from app.db.seed import seed_database


def test_all_15_tables_exist_in_database():
    """Verify that all 15 required relational tables exist in the schema."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    required_tables = {
        "users",
        "cases",
        "extracted_info",
        "locations",
        "ambulances",
        "hospitals",
        "resource_matches",
        "duplicate_relationships",
        "ai_decisions",
        "verification_results",
        "human_reviews",
        "sla_tracking",
        "escalation_events",
        "audit_logs",
        "fairness_records",
    }

    missing_tables = required_tables - existing_tables
    assert not missing_tables, f"Missing required database tables: {missing_tables}"


def test_seed_data_users_ambulances_hospitals():
    """Verify that seed_database initializes realistic simulated users, ambulances, hospitals, and protocols."""
    with SessionLocal() as db:
        seed_database(db)

        # 1. Users
        users = db.query(User).all()
        assert len(users) >= 3
        roles = {u.role for u in users}
        assert UserRole.DISPATCHER in roles
        assert UserRole.SUPERVISOR in roles
        assert UserRole.ADMIN in roles

        # 2. Ambulances
        ambulances = db.query(Ambulance).all()
        assert len(ambulances) >= 10
        for amb in ambulances:
            assert amb.latitude is not None
            assert amb.longitude is not None
            assert amb.vehicle_number.startswith("MH-12")

        # 3. Hospitals
        hospitals = db.query(Hospital).all()
        assert len(hospitals) >= 8
        cardiac_hospitals = [h for h in hospitals if h.has_cardiac_care]
        trauma_hospitals = [h for h in hospitals if h.has_trauma_center]
        assert len(cardiac_hospitals) > 0
        assert len(trauma_hospitals) > 0


def test_multilingual_case_complete_lifecycle():
    """Verify end-to-end relational integrity across all 15 entities for a Marathi emergency case."""
    with SessionLocal() as db:
        seed_database(db)
        dispatcher = db.query(User).filter(User.role == UserRole.DISPATCHER).first()
        amb = db.query(Ambulance).filter(Ambulance.ambulance_type == AmbulanceType.ALS).first()
        hosp = db.query(Hospital).filter(Hospital.has_cardiac_care == True).first()

        # 1. Case (Multilingual input: Marathi)
        case = Case(
            caller_phone="+91-9890012345",
            raw_text="माझ्या आईला छातीत खूप तीव्र दुखत आहे आणि श्वास घेता येत नाहीये, कोथरूड डेपो जवळ",
            language="marathi",
            status=CaseStatus.TRIAGED,
            priority=SeverityLevel.CRITICAL,
        )
        db.add(case)
        db.commit()
        db.refresh(case)

        # 2. ExtractedInfo
        ext_info = ExtractedInfo(
            case_id=case.id,
            emergency_type="CARDIAC",
            symptoms=["छातीत दुखणे (chest pain)", "श्वास घेण्यास त्रास (dyspnea)"],
            extracted_location_text="कोथरूड डेपो (Kothrud Depot)",
            patient_count=1,
            conscious_status="conscious",
            breathing_status="shallow",
            extraction_confidence=0.94,
        )
        db.add(ext_info)

        # 3. Location
        loc = Location(
            case_id=case.id,
            raw_query="Kothrud Depot, Pune",
            formatted_address="Kothrud Bus Depot, Paud Road, Pune 411038",
            latitude=18.5074,
            longitude=73.8077,
            city="Pune",
            state="Maharashtra",
            geocoding_provider="nominatim",
            confidence=0.95,
            is_verified=True,
        )
        db.add(loc)

        # 4. AIDecision
        decision = AIDecision(
            case_id=case.id,
            model_name="grok-beta-http",
            severity_assessment=SeverityLevel.CRITICAL,
            recommended_ambulance_type=AmbulanceType.ALS,
            clinical_rationale="Acute chest pain with respiratory distress in elderly patient indicates high risk of Acute Coronary Syndrome requiring ALS with cardiac monitor and oxygen.",
            confidence_score=0.93,
            latency_ms=310,
        )
        db.add(decision)

        # 5. VerificationResult
        verification = VerificationResult(
            case_id=case.id,
            protocol_code="CARD-01",
            status=VerificationStatus.VERIFIED,
            verified_fields=["symptoms", "severity", "ambulance_type"],
            conflicting_fields=[],
            rag_evidence="Matched Protocol CARD-01: Crushing chest pain radiating to left arm/jaw requiring immediate ALS dispatch.",
            verification_score=0.98,
        )
        db.add(verification)

        # 6. ResourceMatch
        match = ResourceMatch(
            case_id=case.id,
            ambulance_id=amb.id,
            hospital_id=hosp.id,
            ambulance_distance_km=2.1,
            ambulance_eta_minutes=6.5,
            hospital_distance_km=3.4,
            match_score=0.96,
            selection_reason="Nearest available ALS unit with defibrillator and ventilator.",
            is_dispatched=True,
            dispatched_at=datetime.now(timezone.utc),
        )
        db.add(match)

        # 7. SLATracking
        sla = SLATracking(
            case_id=case.id,
            severity_level=SeverityLevel.CRITICAL,
            target_seconds=480,  # 8 min
            started_at=datetime.now(timezone.utc),
            elapsed_seconds=120,
            is_breached=False,
        )
        db.add(sla)

        # 8. HumanReview
        review = HumanReview(
            case_id=case.id,
            dispatcher_id=dispatcher.id,
            review_status=ReviewStatus.APPROVED,
            trigger_reason="Critical cardiac case protocol verification check",
            original_decision={"severity": "CRITICAL", "ambulance": "ALS"},
            final_decision={"severity": "CRITICAL", "ambulance": "ALS"},
            dispatcher_notes="AI recommendation verified and approved immediately. ALS unit dispatched.",
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(review)

        # 9. EscalationEvent (test link)
        escalation = EscalationEvent(
            case_id=case.id,
            escalation_level=EscalationLevel.SUPERVISOR_ALERT,
            triggered_by=EscalationTrigger.LOW_CONFIDENCE,
            reason="Routine priority monitoring for Critical Cardiac triage",
        )
        db.add(escalation)

        # 10. AuditLog
        audit = AuditLog(
            case_id=case.id,
            stage=AuditStage.DISPATCH,
            actor=f"DISPATCHER_{dispatcher.username}",
            action="DISPATCH_APPROVED_AND_SENT",
            details={"ambulance_vehicle": amb.vehicle_number, "hospital": hosp.name},
            latency_ms=85,
        )
        db.add(audit)

        # 11. FairnessRecord
        fairness = FairnessRecord(
            case_id=case.id,
            language_group="Marathi",
            dialect_type="Puneri Marathi",
            predicted_severity=SeverityLevel.CRITICAL,
            verified_severity=SeverityLevel.CRITICAL,
            is_disparity_flagged=False,
            confidence_score=0.93,
            extraction_accuracy=1.0,
        )
        db.add(fairness)

        # 12. DuplicateRelationship (Link to a simulated secondary caller)
        second_case = Case(
            caller_phone="+91-9890099999",
            raw_text="Accident/emergency at Kothrud bus stop, someone collapsed with chest pain",
            language="code-mixed",
            status=CaseStatus.DUPLICATE,
            priority=SeverityLevel.CRITICAL,
        )
        db.add(second_case)
        db.commit()
        db.refresh(second_case)

        duplicate = DuplicateRelationship(
            primary_case_id=case.id,
            duplicate_case_id=second_case.id,
            semantic_similarity=0.88,
            geographic_distance_km=0.15,
            temporal_diff_minutes=3.2,
            overall_confidence=0.92,
            is_confirmed_duplicate=True,
            detection_method="HYBRID_MULTIFACTOR",
        )
        db.add(duplicate)
        db.commit()

        # Query back and verify all relationships
        queried = db.query(Case).filter(Case.id == case.id).first()
        assert queried is not None
        assert queried.extracted_info.emergency_type == "CARDIAC"
        assert queried.location.latitude == 18.5074
        assert len(queried.ai_decisions) == 1
        assert queried.ai_decisions[0].model_name == "grok-beta-http"
        assert len(queried.verification_results) == 1
        assert queried.verification_results[0].status == VerificationStatus.VERIFIED
        assert len(queried.resource_matches) == 1
        assert queried.resource_matches[0].ambulance.vehicle_number == amb.vehicle_number
        assert queried.resource_matches[0].hospital.name == hosp.name
        assert queried.sla_tracking.target_seconds == 480
        assert len(queried.human_reviews) == 1
        assert queried.human_reviews[0].dispatcher.username == dispatcher.username
        assert len(queried.escalation_events) == 1
        assert len(queried.audit_logs) == 1
        assert len(queried.fairness_records) == 1
        assert queried.fairness_records[0].language_group == "Marathi"
        assert len(queried.duplicate_associations) == 1
        assert queried.duplicate_associations[0].duplicate_case_id == second_case.id

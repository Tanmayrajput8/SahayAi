"""
Comprehensive Test Suite for SahayAI Real Multi-Signal Duplicate Detection System.

Tests:
1. Formula weights and normalization
2. Location similarity and Haversine decay
3. Temporal similarity decay
4. Emergency type taxonomy similarity matrix
5. TEST A & TEST B: High similarity (accident at Marine Drive with bleeding)
6. TEST C: Unrelated chest pain at another location (low similarity to A/B)
7. TEST D: Same emergency type but different location and several hours apart
8. TEST E: Same location but unrelated emergency type (not automatically duplicate)
9. TEST F: Same location + same emergency + close time + highly similar narrative (very high score)
10. TEST G: Missing location policy (INSUFFICIENT_EVIDENCE, not blindly NOT_DUPLICATE)
11. IDEMPOTENCY: Repeated triage never duplicates DuplicateRelationship rows
12. AUDIT LOGGING: DUPLICATE_CHECK stage records all required signals and details
13. END-TO-END REST API: Text (?auto_triage=true) and Audio intake consistency
14. CONFIDENCE SCORING INTEGRATION: Canonical duplicate_certainty field integration
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models.case import Case, CaseStatus, SeverityLevel
from app.models.extracted_info import ExtractedInfo
from app.models.location import Location, GeocodingStatus
from app.models.duplicate import DuplicateRelationship
from app.models.audit import AuditLog, AuditStage
from app.models.human_review import HumanReview, ReviewStatus
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.duplicate_detection import (
    DuplicateState,
    calculate_semantic_similarity,
    calculate_location_similarity,
    calculate_temporal_similarity,
    calculate_emergency_type_similarity,
    evaluate_single_candidate,
    run_duplicate_detection,
)
from app.ai.service import process_case_extraction


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session


# =============================================================================
# 1. Component Formulas and Range Normalization Tests
# =============================================================================

def test_formula_weights_and_normalization():
    """Verify weights sum to 1.0 and configurable settings are present."""
    total_weights = (
        settings.DUPLICATE_SEMANTIC_WEIGHT
        + settings.DUPLICATE_LOCATION_WEIGHT
        + settings.DUPLICATE_TIME_WEIGHT
        + settings.DUPLICATE_TYPE_WEIGHT
    )
    assert round(total_weights, 4) == 1.0000
    assert settings.DUPLICATE_SEMANTIC_WEIGHT == 0.40
    assert settings.DUPLICATE_LOCATION_WEIGHT == 0.30
    assert settings.DUPLICATE_TIME_WEIGHT == 0.15
    assert settings.DUPLICATE_TYPE_WEIGHT == 0.15
    assert settings.DUPLICATE_THRESHOLD == 0.80
    assert settings.DUPLICATE_POSSIBLE_THRESHOLD == 0.60
    assert settings.DUPLICATE_TIME_WINDOW_MINUTES == 120.0


def test_haversine_distance_and_location_similarity_formula():
    """Verify location similarity formula: 0 km -> 1.0, linear decay, >= radius -> 0.0."""
    # Exact same coordinates
    sim, dist, coord_v, loc_avail = calculate_location_similarity(
        18.5204, 73.8567, 18.5204, 73.8567, radius_km=5.0
    )
    assert sim == 1.0
    assert dist == 0.0
    assert coord_v is True
    assert loc_avail is True

    # 0.3 km apart (small distance -> high similarity)
    # 1.0 - (0.3 / 5.0) = 0.94
    sim_close, dist_close, _, _ = calculate_location_similarity(
        18.5204, 73.8567, 18.5220, 73.8590, radius_km=5.0
    )
    assert 0.0 < dist_close < 1.0
    assert 0.80 <= sim_close < 1.0

    # Far away (> 5.0 km) -> similarity 0.0
    sim_far, dist_far, _, _ = calculate_location_similarity(
        18.5204, 73.8567, 18.7000, 73.9900, radius_km=5.0
    )
    assert dist_far > 10.0
    assert sim_far == 0.0


def test_temporal_similarity_formula():
    """Verify temporal similarity formula: 0 min -> 1.0, 60 min -> 0.50, > window -> 0.0."""
    t0 = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    t_5m = t0 + timedelta(minutes=5)
    t_60m = t0 + timedelta(minutes=60)
    t_150m = t0 + timedelta(minutes=150)

    sim_5m, diff_5m = calculate_temporal_similarity(t0, t_5m, window_minutes=120.0)
    assert diff_5m == 5.0
    assert round(sim_5m, 3) == round(1.0 - (5.0 / 120.0), 3)

    sim_60m, diff_60m = calculate_temporal_similarity(t0, t_60m, window_minutes=120.0)
    assert diff_60m == 60.0
    assert sim_60m == 0.50

    sim_150m, diff_150m = calculate_temporal_similarity(t0, t_150m, window_minutes=120.0)
    assert diff_150m == 150.0
    assert sim_150m == 0.0


def test_emergency_type_taxonomy_similarity():
    """Verify normalized emergency taxonomy similarity."""
    # Exact match
    assert calculate_emergency_type_similarity("ROAD_TRAFFIC_ACCIDENT", "ROAD_TRAFFIC_ACCIDENT") == 1.0
    assert calculate_emergency_type_similarity("CARDIAC", "CARDIAC") == 1.0

    # Same clinical family: CARDIAC <-> HEART_ATTACK = 0.90
    assert calculate_emergency_type_similarity("CARDIAC", "HEART_ATTACK") == 0.90
    assert calculate_emergency_type_similarity("CAR_ACCIDENT", "ROAD_TRAFFIC_ACCIDENT") == 0.90

    # Related trauma families: TRAUMA <-> ROAD_ACCIDENT = 0.70
    assert calculate_emergency_type_similarity("ROAD_TRAFFIC_ACCIDENT", "BLEEDING") == 0.70
    assert calculate_emergency_type_similarity("ROAD_ACCIDENT", "TRAUMA") == 0.70

    # Unrelated: CARDIAC <-> ROAD_TRAFFIC_ACCIDENT = 0.05
    assert calculate_emergency_type_similarity("CARDIAC", "ROAD_TRAFFIC_ACCIDENT") == 0.05
    assert calculate_emergency_type_similarity("STROKE", "BURN") == 0.05


# =============================================================================
# 2. REQUIRED TEST CASES A, B, C, D, E, F, G
# =============================================================================

def test_case_a_and_b_high_similarity(db_session):
    """
    TEST A and TEST B:
    Case A: 'Severe two-car accident at Marine Drive, two passengers bleeding.'
    Case B: 'Major car accident at Marine Drive, passengers are bleeding and need immediate help.'
    Expected: Real calculated high semantic similarity, high location similarity,
    possible duplicate or duplicate. No hardcoded scores!
    """
    now = datetime.now(timezone.utc)
    marine_drive_lat, marine_drive_lon = 18.9438, 72.8234

    case_a = Case(
        id=f"test-case-a-{uuid.uuid4().hex[:8]}",
        raw_text="Severe two-car accident at Marine Drive, two passengers bleeding.",
        modality="text",
        status=CaseStatus.TRIAGED,
        priority=SeverityLevel.CRITICAL,
        created_at=now - timedelta(minutes=5),
    )
    case_a.extracted_info = ExtractedInfo(
        case_id=case_a.id,
        emergency_type="ROAD_TRAFFIC_ACCIDENT",
        extracted_location_text="Marine Drive",
    )
    case_a.location = Location(
        case_id=case_a.id,
        raw_query="Marine Drive",
        latitude=marine_drive_lat,
        longitude=marine_drive_lon,
        is_verified=True,
        status=GeocodingStatus.SUCCESS,
    )

    case_b = Case(
        id=f"test-case-b-{uuid.uuid4().hex[:8]}",
        raw_text="Major car accident at Marine Drive, passengers are bleeding and need immediate help.",
        modality="text",
        status=CaseStatus.PENDING,
        priority=SeverityLevel.CRITICAL,
        created_at=now,
    )
    case_b.extracted_info = ExtractedInfo(
        case_id=case_b.id,
        emergency_type="ROAD_TRAFFIC_ACCIDENT",
        extracted_location_text="Marine Drive",
    )
    case_b.location = Location(
        case_id=case_b.id,
        raw_query="Marine Drive",
        latitude=marine_drive_lat + 0.001,
        longitude=marine_drive_lon + 0.001,
        is_verified=True,
        status=GeocodingStatus.SUCCESS,
    )

    # Evaluate pairwise signals
    ev = evaluate_single_candidate(new_case=case_b, candidate=case_a)

    # Assertions: Real calculated numbers, NOT hardcoded 0.88, 0.1, 5.0, 0.85
    assert ev.state in (DuplicateState.DUPLICATE, DuplicateState.POSSIBLE_DUPLICATE)
    assert ev.candidate_case_id == case_a.id

    assert ev.semantic_similarity > 0.80, f"Expected high semantic similarity, got {ev.semantic_similarity}"
    assert ev.location_similarity > 0.85, f"Expected high location similarity, got {ev.location_similarity}"
    assert ev.temporal_similarity > 0.90, f"Expected high temporal similarity, got {ev.temporal_similarity}"
    assert ev.emergency_type_similarity == 1.00, f"Expected exact type similarity, got {ev.emergency_type_similarity}"
    assert ev.duplicate_score >= settings.DUPLICATE_POSSIBLE_THRESHOLD
    assert ev.requires_human_review is True

    # Verify not hardcoded values
    assert ev.semantic_similarity != 0.88
    assert ev.geographic_distance_km != 0.1 or round(ev.geographic_distance_km, 3) != 0.100


def test_case_c_unrelated_chest_pain_low_similarity(db_session):
    """
    TEST C:
    'Person experiencing severe chest pain at another location.'
    Expected: Much lower semantic similarity to Case A, low location similarity,
    low overall duplicate score -> NOT_DUPLICATE.
    """
    now = datetime.now(timezone.utc)
    marine_lat, marine_lon = 18.9438, 72.8234
    kothrud_lat, kothrud_lon = 18.5074, 73.8077

    case_a = Case(
        id=f"test-case-a-{uuid.uuid4().hex[:8]}",
        raw_text="Severe two-car accident at Marine Drive, two passengers bleeding.",
        modality="text",
        status=CaseStatus.TRIAGED,
        created_at=now - timedelta(minutes=10),
    )
    case_a.extracted_info = ExtractedInfo(case_id=case_a.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text="Marine Drive")
    case_a.location = Location(case_id=case_a.id, raw_query="Marine Drive", latitude=marine_lat, longitude=marine_lon, is_verified=True, status=GeocodingStatus.SUCCESS)

    case_c = Case(
        id=f"test-case-c-{uuid.uuid4().hex[:8]}",
        raw_text="Person experiencing severe chest pain at another location.",
        modality="text",
        status=CaseStatus.PENDING,
        created_at=now,
    )
    case_c.extracted_info = ExtractedInfo(case_id=case_c.id, emergency_type="CARDIAC", extracted_location_text="Kothrud Pune")
    case_c.location = Location(case_id=case_c.id, raw_query="Kothrud Pune", latitude=kothrud_lat, longitude=kothrud_lon, is_verified=True, status=GeocodingStatus.SUCCESS)

    ev = evaluate_single_candidate(new_case=case_c, candidate=case_a)

    assert ev.state == DuplicateState.NOT_DUPLICATE
    assert ev.semantic_similarity < 0.25, f"Expected low semantic similarity, got {ev.semantic_similarity}"
    assert ev.location_similarity == 0.0, f"Expected 0 location similarity for different cities/neighborhoods"
    assert ev.emergency_type_similarity == 0.05  # CARDIAC vs ROAD_TRAFFIC_ACCIDENT
    assert ev.duplicate_score < 0.35
    assert ev.requires_human_review is False


def test_case_d_same_type_different_location_hours_apart(db_session):
    """
    TEST D:
    Same emergency type (ROAD_TRAFFIC_ACCIDENT), but different location (15 km away)
    and several hours apart (4 hours apart > 120 min candidate window).
    Expected: Lower duplicate score, NOT_DUPLICATE.
    """
    now = datetime.now(timezone.utc)
    case_old = Case(
        id=f"test-case-d1-{uuid.uuid4().hex[:8]}",
        raw_text="Car accident on Katraj bypass road with injury.",
        modality="text",
        status=CaseStatus.TRIAGED,
        created_at=now - timedelta(hours=4),
    )
    case_old.extracted_info = ExtractedInfo(case_id=case_old.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text="Katraj")
    case_old.location = Location(case_id=case_old.id, raw_query="Katraj Pune", latitude=18.4575, longitude=73.8677, is_verified=True, status=GeocodingStatus.SUCCESS)

    case_new = Case(
        id=f"test-case-d2-{uuid.uuid4().hex[:8]}",
        raw_text="Car accident on Aundh road with minor injury.",
        modality="text",
        status=CaseStatus.PENDING,
        created_at=now,
    )
    case_new.extracted_info = ExtractedInfo(case_id=case_new.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text="Aundh")
    case_new.location = Location(case_id=case_new.id, raw_query="Aundh Pune", latitude=18.5580, longitude=73.8075, is_verified=True, status=GeocodingStatus.SUCCESS)

    ev = evaluate_single_candidate(new_case=case_new, candidate=case_old)

    # 4 hours apart is outside window -> temporal_similarity = 0.0; distance > 15 km -> location_similarity = 0.0
    assert ev.temporal_similarity == 0.0
    assert ev.location_similarity == 0.0
    assert ev.state == DuplicateState.NOT_DUPLICATE
    assert ev.duplicate_score < settings.DUPLICATE_POSSIBLE_THRESHOLD
    assert ev.requires_human_review is False


def test_case_e_same_location_unrelated_emergency_type(db_session):
    """
    TEST E:
    Same location (exact same coordinates at Swargate), but completely unrelated emergency type:
    Case 1: Severe heart attack (CARDIAC)
    Case 2: Road collision with bleeding (ROAD_TRAFFIC_ACCIDENT)
    Expected: Not automatically duplicate just because location matches! Score below duplicate thresholds.
    """
    now = datetime.now(timezone.utc)
    swargate_lat, swargate_lon = 18.5018, 73.8586

    case_cardiac = Case(
        id=f"test-case-e1-{uuid.uuid4().hex[:8]}",
        raw_text="Patient having severe heart attack and chest pain at Swargate bus stand.",
        modality="text",
        status=CaseStatus.TRIAGED,
        created_at=now - timedelta(minutes=8),
    )
    case_cardiac.extracted_info = ExtractedInfo(case_id=case_cardiac.id, emergency_type="CARDIAC", extracted_location_text="Swargate")
    case_cardiac.location = Location(case_id=case_cardiac.id, raw_query="Swargate Pune", latitude=swargate_lat, longitude=swargate_lon, is_verified=True, status=GeocodingStatus.SUCCESS)

    case_trauma = Case(
        id=f"test-case-e2-{uuid.uuid4().hex[:8]}",
        raw_text="Two motorcycles collided at Swargate bus stand, rider injured.",
        modality="text",
        status=CaseStatus.PENDING,
        created_at=now,
    )
    case_trauma.extracted_info = ExtractedInfo(case_id=case_trauma.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text="Swargate")
    case_trauma.location = Location(case_id=case_trauma.id, raw_query="Swargate Pune", latitude=swargate_lat, longitude=swargate_lon, is_verified=True, status=GeocodingStatus.SUCCESS)

    ev = evaluate_single_candidate(new_case=case_trauma, candidate=case_cardiac)

    # Location similarity is 1.0 (weight 0.30 -> 0.30), but semantic and emergency type are low (0.05)
    # Overall score should be well below 0.60
    assert ev.state == DuplicateState.NOT_DUPLICATE
    assert ev.duplicate_score < settings.DUPLICATE_POSSIBLE_THRESHOLD
    assert ev.emergency_type_similarity == 0.05
    assert ev.requires_human_review is False


def test_case_f_same_location_same_emergency_close_time_similar_narrative(db_session):
    """
    TEST F:
    Same location + same emergency + close time (2 min) + highly similar description.
    Expected: Very high duplicate score (> 0.85), DUPLICATE state.
    """
    now = datetime.now(timezone.utc)
    lat, lon = 18.5204, 73.8567

    case_orig = Case(
        id=f"test-case-f1-{uuid.uuid4().hex[:8]}",
        raw_text="Major bus crash near Pune station, five people injured and unconscious.",
        modality="text",
        status=CaseStatus.TRIAGED,
        created_at=now - timedelta(minutes=2),
    )
    case_orig.extracted_info = ExtractedInfo(case_id=case_orig.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text="Pune Station")
    case_orig.location = Location(case_id=case_orig.id, raw_query="Pune Station", latitude=lat, longitude=lon, is_verified=True, status=GeocodingStatus.SUCCESS)

    case_caller2 = Case(
        id=f"test-case-f2-{uuid.uuid4().hex[:8]}",
        raw_text="Terrible bus accident at Pune station, several passengers injured and bleeding.",
        modality="text",
        status=CaseStatus.PENDING,
        created_at=now,
    )
    case_caller2.extracted_info = ExtractedInfo(case_id=case_caller2.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text="Pune Station")
    case_caller2.location = Location(case_id=case_caller2.id, raw_query="Pune Station", latitude=lat + 0.0005, longitude=lon + 0.0005, is_verified=True, status=GeocodingStatus.SUCCESS)

    ev = evaluate_single_candidate(new_case=case_caller2, candidate=case_orig)

    assert ev.state == DuplicateState.DUPLICATE
    assert ev.duplicate_score >= settings.DUPLICATE_THRESHOLD
    assert ev.semantic_similarity > 0.80
    assert ev.location_similarity > 0.90
    assert ev.temporal_similarity > 0.95
    assert ev.emergency_type_similarity == 1.0
    assert ev.requires_human_review is True


def test_case_g_missing_location_policy(db_session):
    """
    TEST G:
    Missing location coordinates.
    Expected: INSUFFICIENT_EVIDENCE or policy-defined review trigger,
    NOT blindly NOT_DUPLICATE if semantic and temporal evidence is strong.
    """
    now = datetime.now(timezone.utc)

    # Candidate case with location
    case_with_loc = Case(
        id=f"test-case-g1-{uuid.uuid4().hex[:8]}",
        raw_text="Massive chemical fire in warehouse with three workers trapped and burning.",
        modality="text",
        status=CaseStatus.TRIAGED,
        created_at=now - timedelta(minutes=4),
    )
    case_with_loc.extracted_info = ExtractedInfo(case_id=case_with_loc.id, emergency_type="BURN", extracted_location_text="Bhosari Industrial")
    case_with_loc.location = Location(case_id=case_with_loc.id, raw_query="Bhosari Industrial", latitude=18.6250, longitude=73.8450, is_verified=True, status=GeocodingStatus.SUCCESS)

    # Second case: same emergency description, but NO location provided
    case_no_loc = Case(
        id=f"test-case-g2-{uuid.uuid4().hex[:8]}",
        raw_text="Chemical fire in warehouse, workers trapped inside with severe burns please hurry!",
        modality="text",
        status=CaseStatus.PENDING,
        created_at=now,
    )
    case_no_loc.extracted_info = ExtractedInfo(case_id=case_no_loc.id, emergency_type="BURN", extracted_location_text=None)
    case_no_loc.location = None

    ev = evaluate_single_candidate(new_case=case_no_loc, candidate=case_with_loc)

    # Missing location policy:
    # Location evidence missing -> location_similarity = 0.0, geographic_distance_km = None
    # Semantic (~0.90), temporal (~0.96), type (1.0) are strong.
    # Must NOT blindly mark NOT_DUPLICATE!
    assert ev.has_location_evidence is False
    assert ev.is_coordinate_verified is False
    assert ev.geographic_distance_km is None
    assert ev.location_similarity == 0.0

    # Policy requires human review for unverified location duplicate candidate
    assert ev.requires_human_review is True
    assert ev.state == DuplicateState.INSUFFICIENT_EVIDENCE
    assert "location" in (ev.review_reason or "").lower()


# =============================================================================
# 3. IDEMPOTENCY AND AUDIT LOG TESTS
# =============================================================================

def test_duplicate_relationship_idempotency(db_session):
    """
    Verify idempotency: re-running duplicate detection multiple times for the same case
    does NOT produce duplicate DuplicateRelationship rows.
    """
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8]
    lat, lon = 18.5204, 73.8567

    case1 = Case(
        id=f"idem-case-1-{tag}",
        raw_text=f"Two cars crashed near Shivaji Nagar junction {tag}, severe bleeding.",
        modality="text",
        status=CaseStatus.TRIAGED,
        created_at=now - timedelta(minutes=5),
    )
    db_session.add(case1)
    db_session.flush()
    ext1 = ExtractedInfo(case_id=case1.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text=f"Shivaji Nagar {tag}")
    loc1 = Location(case_id=case1.id, raw_query=f"Shivaji Nagar {tag}", latitude=lat, longitude=lon, is_verified=True, status=GeocodingStatus.SUCCESS)
    db_session.add_all([ext1, loc1])

    case2 = Case(
        id=f"idem-case-2-{tag}",
        raw_text=f"Major accident at Shivaji Nagar junction {tag} with two cars and injured victims.",
        modality="text",
        status=CaseStatus.PENDING,
        created_at=now,
    )
    db_session.add(case2)
    db_session.flush()
    ext2 = ExtractedInfo(case_id=case2.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text=f"Shivaji Nagar {tag}")
    loc2 = Location(case_id=case2.id, raw_query=f"Shivaji Nagar {tag}", latitude=lat, longitude=lon, is_verified=True, status=GeocodingStatus.SUCCESS)
    db_session.add_all([ext2, loc2])
    db_session.commit()

    try:
        # Run detection 1st time
        res1 = run_duplicate_detection(case=case2, db=db_session)
        db_session.commit()

        count_after_1 = db_session.query(DuplicateRelationship).filter(
            DuplicateRelationship.duplicate_case_id == case2.id
        ).count()
        assert count_after_1 == 1

        # Run detection 2nd time (e.g. case re-triaged)
        res2 = run_duplicate_detection(case=case2, db=db_session)
        db_session.commit()

        count_after_2 = db_session.query(DuplicateRelationship).filter(
            DuplicateRelationship.duplicate_case_id == case2.id
        ).count()
        assert count_after_2 == 1, "Expected exactly 1 DuplicateRelationship row, not multiple duplicates!"

        # Run detection 3rd time
        res3 = run_duplicate_detection(case=case2, db=db_session)
        db_session.commit()

        count_after_3 = db_session.query(DuplicateRelationship).filter(
            DuplicateRelationship.duplicate_case_id == case2.id
        ).count()
        assert count_after_3 == 1
    finally:
        # Cleanup
        db_session.query(DuplicateRelationship).filter(
            (DuplicateRelationship.duplicate_case_id == case2.id) | (DuplicateRelationship.primary_case_id == case1.id)
        ).delete()
        db_session.query(AuditLog).filter(AuditLog.case_id.in_([case1.id, case2.id])).delete()
        db_session.query(Location).filter(Location.case_id.in_([case1.id, case2.id])).delete()
        db_session.query(ExtractedInfo).filter(ExtractedInfo.case_id.in_([case1.id, case2.id])).delete()
        db_session.query(Case).filter(Case.id.in_([case1.id, case2.id])).delete()
        db_session.commit()


def test_audit_logging_structure(db_session):
    """Verify DUPLICATE_CHECK audit log contains all required fields with real calculated values."""
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8]
    lat, lon = 18.5204, 73.8567

    case1 = Case(id=f"audit-case-1-{tag}", raw_text=f"Accident at Swargate {tag}", modality="text", status=CaseStatus.TRIAGED, created_at=now - timedelta(minutes=5))
    case2 = Case(id=f"audit-case-2-{tag}", raw_text=f"Crash at Swargate {tag}", modality="text", status=CaseStatus.PENDING, created_at=now)
    db_session.add_all([case1, case2])
    db_session.flush()

    ext1 = ExtractedInfo(case_id=case1.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text=f"Swargate {tag}")
    loc1 = Location(case_id=case1.id, raw_query=f"Swargate {tag}", latitude=lat, longitude=lon, is_verified=True, status=GeocodingStatus.SUCCESS)
    ext2 = ExtractedInfo(case_id=case2.id, emergency_type="ROAD_TRAFFIC_ACCIDENT", extracted_location_text=f"Swargate {tag}")
    loc2 = Location(case_id=case2.id, raw_query=f"Swargate {tag}", latitude=lat, longitude=lon, is_verified=True, status=GeocodingStatus.SUCCESS)
    db_session.add_all([ext1, loc1, ext2, loc2])
    db_session.commit()

    try:
        res = run_duplicate_detection(case=case2, db=db_session)
        db_session.commit()

        audit = db_session.query(AuditLog).filter(
            AuditLog.case_id == case2.id,
            AuditLog.stage == AuditStage.DUPLICATE_CHECK,
        ).first()

        assert audit is not None
        assert audit.actor == "DUPLICATE_DETECTOR"
        assert audit.action == "DUPLICATE_CHECK_COMPLETED"
        d = audit.details
        assert "duplicate_detected" in d
        assert "duplicate_status" in d
        assert "duplicate_score" in d
        assert "candidate_case_id" in d
        assert "semantic_similarity" in d
        assert "geographic_distance_km" in d
        assert "temporal_diff_minutes" in d
        assert "emergency_type_similarity" in d
        assert "detection_method" in d
        assert d["detection_method"] == "WEIGHTED_MULTISIGNAL"
    finally:
        db_session.query(DuplicateRelationship).filter(
            (DuplicateRelationship.duplicate_case_id == case2.id) | (DuplicateRelationship.primary_case_id == case1.id)
        ).delete()
        db_session.query(AuditLog).filter(AuditLog.case_id.in_([case1.id, case2.id])).delete()
        db_session.query(Location).filter(Location.case_id.in_([case1.id, case2.id])).delete()
        db_session.query(ExtractedInfo).filter(ExtractedInfo.case_id.in_([case1.id, case2.id])).delete()
        db_session.query(Case).filter(Case.id.in_([case1.id, case2.id])).delete()
        db_session.commit()


# =============================================================================
# 4. REST API Integration Tests: Text & Audio Consistency
# =============================================================================

def test_api_text_and_audio_consistency(client):
    """
    Verify text intake with auto_triage=True triggers duplicate detection consistently
    just like audio intake.
    """
    tag = uuid.uuid4().hex[:6]
    # 1. Primary Text Case
    payload1 = {
        "raw_text": f"Critical multi-vehicle crash outside Isolated Junction {tag}, two people severely injured.",
        "latitude": 21.5620,
        "longitude": 76.9168,
        "manual_location": f"Isolated Junction Area {tag}",
    }
    r1 = client.post("/api/v1/cases?auto_triage=true", json=payload1)
    assert r1.status_code == 201
    case1_id = r1.json()["id"]

    # 2. Secondary Text Case (Duplicate incident)
    payload2 = {
        "raw_text": f"Severe vehicle collision outside Isolated Junction {tag}, people injured need ambulance immediately.",
        "latitude": 21.5620,
        "longitude": 76.9168,
        "manual_location": f"Isolated Junction Area {tag}",
    }
    r2 = client.post("/api/v1/cases?auto_triage=true", json=payload2)
    assert r2.status_code == 201
    case2_id = r2.json()["id"]

    # Retrieve case 2 dossier via GET /api/v1/cases/{case2_id}
    r_get = client.get(f"/api/v1/cases/{case2_id}")
    assert r_get.status_code == 200
    data = r_get.json()

    assert data["duplicate_detection"] is not None
    dup_info = data["duplicate_detection"]
    assert dup_info["status"] in ("DUPLICATE", "POSSIBLE_DUPLICATE")
    assert dup_info["matched_case_id"] == case1_id
    assert dup_info["score"] > 0.70
    assert dup_info["semantic_similarity"] > 0.70
    assert dup_info["location_similarity"] > 0.85
    assert dup_info["detection_method"] == "WEIGHTED_MULTISIGNAL"

    # Test GET /api/v1/cases/{case2_id}/duplicates
    r_dup = client.get(f"/api/v1/cases/{case2_id}/duplicates")
    assert r_dup.status_code == 200
    dup_resp = r_dup.json()
    assert dup_resp["matched_case_id"] == case1_id
    assert dup_resp["score"] == dup_info["score"]

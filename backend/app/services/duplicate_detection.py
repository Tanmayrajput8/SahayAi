"""
SahayAI Multi-Signal Real Duplicate Detection Engine.

Implements real multi-signal duplicate emergency detection using:
1. Semantic Similarity (40%) - Vector embeddings & cosine similarity over emergency narrative.
2. Geographic Distance & Location Similarity (30%) - Haversine great-circle calculation & linear decay.
3. Temporal Proximity (15%) - Elapsed minutes difference within configurable candidate window.
4. Clinical Emergency Taxonomy Similarity (15%) - Deterministic explainable taxonomy matrix.

Combines signals using:
duplicate_score =
    0.40 * semantic_similarity
  + 0.30 * location_similarity
  + 0.15 * temporal_similarity
  + 0.15 * emergency_type_similarity

States:
- DUPLICATE (score >= DUPLICATE_THRESHOLD and location verified)
- POSSIBLE_DUPLICATE (score >= DUPLICATE_POSSIBLE_THRESHOLD)
- INSUFFICIENT_EVIDENCE (missing location or clinical data with strong remaining signals)
- NOT_DUPLICATE (score < DUPLICATE_POSSIBLE_THRESHOLD)

Zero mocked scores. Zero fake values. Fully idempotent and explainable.
"""
from __future__ import annotations

import enum
import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.case import Case, CaseStatus
from app.models.extracted_info import ExtractedInfo
from app.models.duplicate import DuplicateRelationship
from app.models.human_review import HumanReview, ReviewStatus
from app.models.audit import AuditLog, AuditStage
from app.services.routing.fallback import haversine_distance_km

logger = logging.getLogger(__name__)


class DuplicateState(str, enum.Enum):
    NOT_DUPLICATE = "NOT_DUPLICATE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    DUPLICATE = "DUPLICATE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


# =============================================================================
# 1. Normalized Emergency Taxonomy & Clinical Similarity
# =============================================================================

# Categorical taxonomy clusters for explainable emergency-type comparison
TAXONOMY_CLUSTERS: Dict[str, List[str]] = {
    "CARDIAC": [
        "CARDIAC", "HEART", "CHEST_PAIN", "ANGINA", "MYOCARDIAL", "INFARCTION",
        "STEMI", "CORONARY", "CARDIAC_ARREST", "HEART_ATTACK", "HEART_EMERGENCY"
    ],
    "TRAUMA_ROAD": [
        "ROAD_TRAFFIC_ACCIDENT", "ROAD_ACCIDENT", "CAR_ACCIDENT", "TRAFFIC_ACCIDENT",
        "VEHICLE_COLLISION", "ACCIDENT", "COLLISION", "MVA", "MOTORCYCLE", "HIT_AND_RUN"
    ],
    "TRAUMA_GENERAL": [
        "TRAUMA", "BLEEDING", "HEMORRHAGE", "FALL", "FRACTURE", "PHYSICAL_TRAUMA",
        "HEAD_INJURY", "INJURY", "STAB", "LACERATION", "ASSAULT"
    ],
    "RESPIRATORY": [
        "RESPIRATORY", "BREATHING", "BREATHING_DIFFICULTY", "ASTHMA", "CHOKING",
        "DYSPNEA", "SUFFOCATION", "ASPHYXIA", "SHORTNESS_OF_BREATH", "COPD"
    ],
    "STROKE": [
        "STROKE", "PARALYSIS", "CVA", "FACIAL_DROOP", "HEMIPLEGIA", "SLURRED_SPEECH", "FAST"
    ],
    "BURNS": [
        "BURN", "BURNS", "FIRE", "THERMAL_BURN", "SCALD", "SMOKE_INHALATION", "FLAME"
    ],
    "PEDIATRIC": [
        "PEDIATRIC", "INFANT", "CHILD", "NEONATAL", "BABY", "TODDLER"
    ],
    "GENERAL": [
        "GENERAL_MEDICAL", "UNCONSCIOUS", "ALTERED_MENTAL_STATUS", "SYNCOPE",
        "FEVER", "UNKNOWN", "SEIZURE", "POISONING", "OVERDOSE"
    ],
}


def _canonicalize_emergency_type(raw_type: Optional[str]) -> str:
    """Normalize raw emergency type string to canonical uppercase snake_case."""
    if not raw_type:
        return "UNKNOWN"
    clean = raw_type.strip().upper()
    for ch in [" ", "-", "/", "\\", ",", ";"]:
        clean = clean.replace(ch, "_")
    while "__" in clean:
        clean = clean.replace("__", "_")
    return clean.strip("_")


def _find_taxonomy_family(canon_type: str) -> Optional[str]:
    """Find matching taxonomy family for a canonical emergency type."""
    if not canon_type or canon_type == "UNKNOWN":
        return None
    for family, keywords in TAXONOMY_CLUSTERS.items():
        if any(kw in canon_type for kw in keywords):
            return family
    return None


def calculate_emergency_type_similarity(type1: Optional[str], type2: Optional[str]) -> float:
    """
    Compute explainable emergency type similarity between two clinical categories.
    
    Rules:
    - Exact match (after canonicalization): 1.00
    - Same clinical family (e.g., CARDIAC <-> HEART_ATTACK, ROAD_ACCIDENT <-> COLLISION): 0.90
    - Closely related families (e.g., TRAUMA_ROAD <-> TRAUMA_GENERAL): 0.70
    - Cross-symptom overlap (e.g., RESPIRATORY <-> CARDIAC): 0.35
    - One is generic/unknown: 0.20
    - Unrelated categories (e.g., CARDIAC <-> ROAD_ACCIDENT): 0.05
    """
    c1 = _canonicalize_emergency_type(type1)
    c2 = _canonicalize_emergency_type(type2)

    # 1. Exact string match
    if c1 == c2 and c1 != "UNKNOWN":
        return 1.00

    f1 = _find_taxonomy_family(c1)
    f2 = _find_taxonomy_family(c2)

    if not f1 or not f2:
        return 0.20

    # 2. Same family
    if f1 == f2:
        return 0.90

    # 3. Closely related trauma families
    if {f1, f2} == {"TRAUMA_ROAD", "TRAUMA_GENERAL"}:
        return 0.70

    # 4. Cross-symptom overlaps (e.g. dyspnea and cardiac distress)
    if {f1, f2} == {"CARDIAC", "RESPIRATORY"}:
        return 0.35

    # 5. General medical umbrella
    if "GENERAL" in (f1, f2):
        return 0.25

    # 6. Unrelated categories
    return 0.05


# =============================================================================
# 2. Semantic Similarity via Dense Embeddings
# =============================================================================

def _vector_cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate exact cosine similarity between two numeric vectors."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 < 1e-9 or norm2 < 1e-9:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm1 * norm2)))


def calculate_semantic_similarity(
    text1: Optional[str],
    text2: Optional[str],
    provider: Optional[Any] = None,
) -> float:
    """
    Compute real semantic similarity between two emergency descriptions
    using normalized dense embedding vectors and cosine similarity.
    Bounded strictly to [0.0, 1.0].
    """
    t1 = (text1 or "").strip()
    t2 = (text2 or "").strip()

    if not t1 or not t2:
        return 0.0

    if t1.lower() == t2.lower():
        return 1.00

    if provider is not None:
        emb_provider = provider
    else:
        from app.ai.rag.embeddings.factory import get_embedding_provider
        emb_provider = get_embedding_provider()

    try:
        vec1 = emb_provider.get_embedding(t1)
        vec2 = emb_provider.get_embedding(t2)
        sim = _vector_cosine_similarity(vec1, vec2)
        # Cosine similarity is bounded in [-1.0, 1.0]; for positive semantic projections in [0, 1]
        return round(max(0.0, min(1.0, float(sim))), 4)
    except Exception as exc:
        logger.warning("Embedding cosine similarity calculation failed (%s); using token Jaccard fallback.", exc)
        # Word-level Jaccard fallback
        tokens1 = set(t1.lower().split())
        tokens2 = set(t2.lower().split())
        if not tokens1 or not tokens2:
            return 0.0
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
        return round(max(0.0, min(1.0, jaccard)), 4)


# =============================================================================
# 3. Location Similarity via Haversine Distance & Fallback Text Matching
# =============================================================================

def calculate_location_similarity(
    lat1: Optional[float],
    lon1: Optional[float],
    lat2: Optional[float],
    lon2: Optional[float],
    text_loc1: Optional[str] = None,
    text_loc2: Optional[str] = None,
    radius_km: float = 5.0,
) -> Tuple[float, Optional[float], bool, bool]:
    """
    Compute location similarity and distance in kilometers.
    
    Returns:
    - similarity: float (0.0 to 1.0)
    - distance_km: Optional[float] (None if coordinates unavailable)
    - is_coordinate_verified: bool (True if both have valid lat/lon)
    - has_location_evidence: bool (True if either coordinates or textual location available)
    
    Behavior:
    - 0 km -> similarity 1.0
    - linear decay within radius_km: max(0.0, 1.0 - (dist / radius_km))
    - distance >= radius_km -> similarity 0.0
    - If coordinates missing but text locations available: fallback string similarity
      with is_coordinate_verified = False.
    - If completely missing: (0.0, None, False, False)
    """
    has_coords1 = lat1 is not None and lon1 is not None and not (lat1 == 0.0 and lon1 == 0.0)
    has_coords2 = lat2 is not None and lon2 is not None and not (lat2 == 0.0 and lon2 == 0.0)

    # 1. Real Coordinate-verified Haversine calculation
    if has_coords1 and has_coords2:
        dist_km = haversine_distance_km(float(lat1), float(lon1), float(lat2), float(lon2))
        dist_km = round(dist_km, 3)
        effective_radius = max(0.1, radius_km)
        similarity = max(0.0, 1.0 - (dist_km / effective_radius))
        return round(max(0.0, min(1.0, similarity)), 4), dist_km, True, True

    # 2. Textual location fallback (clearly marked as NOT coordinate-verified)
    t1 = (text_loc1 or "").strip().lower()
    t2 = (text_loc2 or "").strip().lower()
    if t1 and t2:
        # Normalized token Jaccard similarity for address/landmark text
        toks1 = set(w for w in t1.replace(",", " ").replace("-", " ").split() if len(w) > 2)
        toks2 = set(w for w in t2.replace(",", " ").replace("-", " ").split() if len(w) > 2)
        if toks1 and toks2:
            intersection = len(toks1 & toks2)
            union = len(toks1 | toks2)
            jaccard = intersection / union if union > 0 else 0.0
            # If high token overlap, cap textual similarity at 0.85 since coordinates are unverified
            sim = min(0.85, jaccard * 1.1)
            return round(sim, 4), None, False, True
        return 0.0, None, False, True

    # 3. Completely missing location evidence
    return 0.0, None, False, False


# =============================================================================
# 4. Temporal Similarity via Elapsed Minutes & Candidate Window
# =============================================================================

def calculate_temporal_similarity(
    time1: datetime,
    time2: datetime,
    window_minutes: float = 120.0,
) -> Tuple[float, float]:
    """
    Calculate elapsed temporal difference in minutes and normalized similarity.
    
    Formula:
    temporal_diff_minutes = abs((time1 - time2).total_seconds()) / 60.0
    If diff <= window_minutes: max(0.0, 1.0 - (diff / window_minutes))
    If diff > window_minutes: 0.0
    
    Returns:
    - similarity: float (0.0 to 1.0)
    - temporal_diff_minutes: float
    """
    # Normalize datetime timezone awareness to avoid subtraction errors
    t1 = time1.replace(tzinfo=None) if time1.tzinfo else time1
    t2 = time2.replace(tzinfo=None) if time2.tzinfo else time2

    diff_seconds = abs((t1 - t2).total_seconds())
    diff_minutes = round(diff_seconds / 60.0, 2)

    effective_window = max(1.0, window_minutes)
    if diff_minutes <= effective_window:
        sim = max(0.0, 1.0 - (diff_minutes / effective_window))
    else:
        sim = 0.0

    return round(max(0.0, min(1.0, sim)), 4), diff_minutes


# =============================================================================
# 5. Data Structures for Signal Breakdown and Detection Result
# =============================================================================

@dataclass
class DuplicateCandidateEvaluation:
    candidate_case_id: str
    duplicate_score: float
    state: DuplicateState
    semantic_similarity: float
    location_similarity: float
    temporal_similarity: float
    emergency_type_similarity: float
    geographic_distance_km: Optional[float]
    temporal_diff_minutes: float
    is_coordinate_verified: bool
    has_location_evidence: bool
    requires_human_review: bool
    review_reason: Optional[str]
    detection_method: str = "WEIGHTED_MULTISIGNAL"
    policy_notes: str = ""


@dataclass
class DuplicateDetectionResult:
    case_id: str
    duplicate_detected: bool
    state: DuplicateState
    best_candidate_id: Optional[str] = None
    duplicate_score: float = 0.0
    semantic_similarity: float = 0.0
    location_similarity: float = 0.0
    temporal_similarity: float = 0.0
    emergency_type_similarity: float = 0.0
    geographic_distance_km: Optional[float] = None
    temporal_diff_minutes: float = 0.0
    is_coordinate_verified: bool = False
    has_location_evidence: bool = False
    requires_human_review: bool = False
    review_trigger_reason: Optional[str] = None
    detection_method: str = "WEIGHTED_MULTISIGNAL"
    evaluated_candidates_count: int = 0
    policy_notes: str = ""

    def to_audit_details(self) -> Dict[str, Any]:
        """Format immutable audit trail dictionary."""
        return {
            "duplicate_detected": self.duplicate_detected,
            "duplicate_status": self.state.value,
            "duplicate_score": round(self.duplicate_score, 4),
            "candidate_case_id": self.best_candidate_id,
            "semantic_similarity": round(self.semantic_similarity, 4),
            "geographic_distance_km": self.geographic_distance_km,
            "location_similarity": round(self.location_similarity, 4),
            "temporal_diff_minutes": round(self.temporal_diff_minutes, 2),
            "temporal_similarity": round(self.temporal_similarity, 4),
            "emergency_type_similarity": round(self.emergency_type_similarity, 4),
            "detection_method": self.detection_method,
            "formula": "0.40*semantic + 0.30*location + 0.15*temporal + 0.15*type",
            "weights": {
                "semantic": settings.DUPLICATE_SEMANTIC_WEIGHT,
                "location": settings.DUPLICATE_LOCATION_WEIGHT,
                "temporal": settings.DUPLICATE_TIME_WEIGHT,
                "emergency_type": settings.DUPLICATE_TYPE_WEIGHT,
            },
            "location_coordinate_verified": self.is_coordinate_verified,
            "location_evidence_available": self.has_location_evidence,
            "evaluated_candidates_count": self.evaluated_candidates_count,
            "missing_data_policy_applied": self.policy_notes,
        }


# =============================================================================
# 6. Candidate Search and Multi-Signal Scoring Engine
# =============================================================================

def find_candidate_cases(
    case: Case,
    db: Session,
    window_minutes: Optional[float] = None,
    limit: int = 50,
) -> List[Case]:
    """
    Search historical cases within configurable candidate temporal window.
    Filters out current case itself and cancelled cases.
    Does NOT scan the entire historical database unnecessarily.
    """
    window = window_minutes if window_minutes is not None else settings.DUPLICATE_TIME_WINDOW_MINUTES
    reference_time = case.created_at or datetime.now(timezone.utc)
    if reference_time.tzinfo:
        reference_time = reference_time.replace(tzinfo=None)

    earliest_cutoff = reference_time - timedelta(minutes=window)
    latest_cutoff = reference_time + timedelta(minutes=window)

    query = (
        db.query(Case)
        .filter(
            Case.id != case.id,
            Case.status != CaseStatus.CANCELLED,
            Case.created_at >= earliest_cutoff,
            Case.created_at <= latest_cutoff,
        )
        .order_by(Case.created_at.desc())
        .limit(limit)
    )
    return query.all()


def evaluate_single_candidate(
    new_case: Case,
    candidate: Case,
    embedding_provider: Optional[Any] = None,
) -> DuplicateCandidateEvaluation:
    """
    Compute real calculated signals between new case and a single candidate case.
    
    Formula:
    duplicate_score =
        0.40 * semantic_similarity
      + 0.30 * location_similarity
      + 0.15 * temporal_similarity
      + 0.15 * emergency_type_similarity
    """
    w_sem = settings.DUPLICATE_SEMANTIC_WEIGHT
    w_loc = settings.DUPLICATE_LOCATION_WEIGHT
    w_tim = settings.DUPLICATE_TIME_WEIGHT
    w_typ = settings.DUPLICATE_TYPE_WEIGHT

    thresh_dup = settings.DUPLICATE_THRESHOLD
    thresh_pos = settings.DUPLICATE_POSSIBLE_THRESHOLD

    # 1. Semantic Similarity (40%)
    t_new = new_case.raw_text or ""
    t_cand = candidate.raw_text or ""
    sem_sim = calculate_semantic_similarity(t_new, t_cand, provider=embedding_provider)

    # 2. Location Similarity (30%)
    loc_new = new_case.location
    loc_cand = candidate.location
    lat_new = loc_new.latitude if loc_new else None
    lon_new = loc_new.longitude if loc_new else None
    lat_cand = loc_cand.latitude if loc_cand else None
    lon_cand = loc_cand.longitude if loc_cand else None

    # Text location fallbacks
    ext_new = new_case.extracted_info
    ext_cand = candidate.extracted_info
    txt_new = (ext_new.extracted_location_text if ext_new else None) or (loc_new.raw_query if loc_new else None)
    txt_cand = (ext_cand.extracted_location_text if ext_cand else None) or (loc_cand.raw_query if loc_cand else None)

    loc_sim, dist_km, coord_verif, loc_avail = calculate_location_similarity(
        lat1=lat_new,
        lon1=lon_new,
        lat2=lat_cand,
        lon2=lon_cand,
        text_loc1=txt_new,
        text_loc2=txt_cand,
        radius_km=settings.DUPLICATE_LOCATION_RADIUS_KM,
    )

    # 3. Temporal Similarity (15%)
    now_dt = datetime.now(timezone.utc)
    time_new = new_case.created_at or now_dt
    time_cand = candidate.created_at or now_dt
    temp_sim, time_diff_min = calculate_temporal_similarity(
        time_new,
        time_cand,
        window_minutes=settings.DUPLICATE_TIME_WINDOW_MINUTES,
    )

    # 4. Emergency Type Similarity (15%)
    type_new = ext_new.emergency_type if ext_new else None
    type_cand = ext_cand.emergency_type if ext_cand else None
    type_sim = calculate_emergency_type_similarity(type_new, type_cand)

    # 5. Weighted Score Calculation
    calculated_score = (
        (w_sem * sem_sim)
        + (w_loc * loc_sim)
        + (w_tim * temp_sim)
        + (w_typ * type_sim)
    )
    duplicate_score = round(max(0.0, min(1.0, calculated_score)), 4)

    # 6. Missing Location Policy & State Determination
    policy_notes = ""
    req_review = False
    review_reason = None

    if not loc_avail:
        # Location evidence is missing on either or both cases.
        # DO NOT invent a fake location score or blindly conclude NOT_DUPLICATE.
        # Max achievable partial score without location is 0.70.
        partial_score = (w_sem * sem_sim) + (w_tim * temp_sim) + (w_typ * type_sim)
        policy_notes = "Location missing; evaluated using semantic, temporal, and type signals."

        if partial_score >= 0.50:
            # Strong evidence across all other signals: Mark INSUFFICIENT_EVIDENCE
            # Flag for dispatcher location verification before duplicate confirmation.
            state = DuplicateState.INSUFFICIENT_EVIDENCE
            req_review = True
            review_reason = (
                f"Duplicate check: High narrative match ({sem_sim:.2f}) with Case #{candidate.id[:8]}, "
                f"but location coordinates are missing. Requires dispatcher location verification."
            )
        else:
            state = DuplicateState.NOT_DUPLICATE

    elif not coord_verif:
        # Textual match used because GPS coordinates were not available
        policy_notes = "Textual location fallback match; unverified coordinates."
        if duplicate_score >= thresh_dup:
            state = DuplicateState.POSSIBLE_DUPLICATE
            req_review = True
            review_reason = f"Potential duplicate of #{candidate.id[:8]} (Score: {duplicate_score:.2f}, text location match)"
        elif duplicate_score >= thresh_pos:
            state = DuplicateState.POSSIBLE_DUPLICATE
            req_review = True
            review_reason = f"Possible duplicate of #{candidate.id[:8]} (Score: {duplicate_score:.2f})"
        else:
            state = DuplicateState.NOT_DUPLICATE

    else:
        # Full coordinate-verified multi-signal evaluation
        policy_notes = f"Coordinate-verified: distance {dist_km:.2f} km."
        if duplicate_score >= thresh_dup:
            state = DuplicateState.DUPLICATE
            req_review = True
            review_reason = (
                f"Potential duplicate incident detected at same location: #{candidate.id[:8]} "
                f"(Score: {duplicate_score:.2f}, Distance: {dist_km:.2f}km, Elapsed: {time_diff_min:.1f}min)"
            )
        elif duplicate_score >= thresh_pos:
            state = DuplicateState.POSSIBLE_DUPLICATE
            req_review = True
            review_reason = (
                f"Possible duplicate incident: #{candidate.id[:8]} "
                f"(Score: {duplicate_score:.2f}, Distance: {dist_km:.2f}km)"
            )
        else:
            state = DuplicateState.NOT_DUPLICATE

    return DuplicateCandidateEvaluation(
        candidate_case_id=candidate.id,
        duplicate_score=duplicate_score,
        state=state,
        semantic_similarity=sem_sim,
        location_similarity=loc_sim,
        temporal_similarity=temp_sim,
        emergency_type_similarity=type_sim,
        geographic_distance_km=dist_km,
        temporal_diff_minutes=time_diff_min,
        is_coordinate_verified=coord_verif,
        has_location_evidence=loc_avail,
        requires_human_review=req_review,
        review_reason=review_reason,
        detection_method="WEIGHTED_MULTISIGNAL",
        policy_notes=policy_notes,
    )


def run_duplicate_detection(
    case: Case,
    db: Session,
    provider: Optional[Any] = None,
) -> DuplicateDetectionResult:
    """
    Execute full real duplicate detection pipeline for an emergency case.
    
    Guarantees:
    - Gathers candidate pool from configurable temporal window (e.g. 120 minutes).
    - Computes real calculated signals for every candidate.
    - Picks candidate with highest valid duplicate score.
    - Idempotently creates or updates DuplicateRelationship (no duplicate rows!).
    - Flags human review when threshold is reached without deleting cases.
    - Writes immutable AuditLog entry with stage DUPLICATE_CHECK.
    """
    candidates = find_candidate_cases(case=case, db=db)
    logger.info("Duplicate check for case %s: %d candidates found in window.", case.id, len(candidates))

    if not candidates:
        # No candidates in temporal window
        res = DuplicateDetectionResult(
            case_id=case.id,
            duplicate_detected=False,
            state=DuplicateState.NOT_DUPLICATE,
            best_candidate_id=None,
            duplicate_score=0.0,
            evaluated_candidates_count=0,
            policy_notes="No active candidate cases in configured time window.",
        )
        _record_duplicate_audit_log(case=case, db=db, result=res)
        return res

    # Evaluate all candidates and select best match
    evaluations: List[DuplicateCandidateEvaluation] = []
    for cand in candidates:
        ev = evaluate_single_candidate(new_case=case, candidate=cand, embedding_provider=provider)
        evaluations.append(ev)

    # Sort descending by duplicate_score
    evaluations.sort(key=lambda x: x.duplicate_score, reverse=True)
    best = evaluations[0]

    is_duplicate_flag = best.state in (DuplicateState.DUPLICATE, DuplicateState.POSSIBLE_DUPLICATE)

    result = DuplicateDetectionResult(
        case_id=case.id,
        duplicate_detected=is_duplicate_flag,
        state=best.state,
        best_candidate_id=best.candidate_case_id,
        duplicate_score=best.duplicate_score,
        semantic_similarity=best.semantic_similarity,
        location_similarity=best.location_similarity,
        temporal_similarity=best.temporal_similarity,
        emergency_type_similarity=best.emergency_type_similarity,
        geographic_distance_km=best.geographic_distance_km,
        temporal_diff_minutes=best.temporal_diff_minutes,
        is_coordinate_verified=best.is_coordinate_verified,
        has_location_evidence=best.has_location_evidence,
        requires_human_review=best.requires_human_review,
        review_trigger_reason=best.review_reason,
        detection_method="WEIGHTED_MULTISIGNAL",
        evaluated_candidates_count=len(candidates),
        policy_notes=best.policy_notes,
    )

    # Idempotent DuplicateRelationship persistence
    if is_duplicate_flag or best.state == DuplicateState.INSUFFICIENT_EVIDENCE:
        _upsert_duplicate_relationship(
            primary_id=best.candidate_case_id,
            duplicate_id=case.id,
            eval_data=best,
            db=db,
        )

    # Immutable Audit Log
    _record_duplicate_audit_log(case=case, db=db, result=result)

    return result


def _upsert_duplicate_relationship(
    primary_id: str,
    duplicate_id: str,
    eval_data: DuplicateCandidateEvaluation,
    db: Session,
) -> DuplicateRelationship:
    """
    Idempotently insert or update DuplicateRelationship between two cases.
    Guarantees no redundant A->B relationship rows on re-triage.
    """
    existing: Optional[DuplicateRelationship] = (
        db.query(DuplicateRelationship)
        .filter(
            (
                (DuplicateRelationship.primary_case_id == primary_id)
                & (DuplicateRelationship.duplicate_case_id == duplicate_id)
            )
            | (
                (DuplicateRelationship.primary_case_id == duplicate_id)
                & (DuplicateRelationship.duplicate_case_id == primary_id)
            )
        )
        .first()
    )

    if existing:
        # Update existing relationship with newly calculated real metrics
        existing.semantic_similarity = eval_data.semantic_similarity
        existing.geographic_distance_km = eval_data.geographic_distance_km or 0.0
        existing.temporal_diff_minutes = eval_data.temporal_diff_minutes
        existing.emergency_type_similarity = eval_data.emergency_type_similarity
        existing.overall_confidence = eval_data.duplicate_score
        existing.detection_method = "WEIGHTED_MULTISIGNAL"
        return existing

    # Create new relationship
    new_rel = DuplicateRelationship(
        primary_case_id=primary_id,
        duplicate_case_id=duplicate_id,
        semantic_similarity=eval_data.semantic_similarity,
        geographic_distance_km=eval_data.geographic_distance_km or 0.0,
        temporal_diff_minutes=eval_data.temporal_diff_minutes,
        emergency_type_similarity=eval_data.emergency_type_similarity,
        overall_confidence=eval_data.duplicate_score,
        is_confirmed_duplicate=False,
        detection_method="WEIGHTED_MULTISIGNAL",
    )
    db.add(new_rel)
    return new_rel


def _record_duplicate_audit_log(
    case: Case,
    db: Session,
    result: DuplicateDetectionResult,
) -> AuditLog:
    """Record immutable DUPLICATE_CHECK audit trail."""
    audit_dup = AuditLog(
        case_id=case.id,
        stage=AuditStage.DUPLICATE_CHECK,
        actor="DUPLICATE_DETECTOR",
        action="DUPLICATE_CHECK_COMPLETED",
        details=result.to_audit_details(),
    )
    db.add(audit_dup)
    return audit_dup

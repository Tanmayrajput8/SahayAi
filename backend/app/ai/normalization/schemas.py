"""Schemas for Multilingual Medical Terminology Normalization."""
import enum
from typing import List, Optional
from pydantic import BaseModel, Field

from app.models.case import SeverityLevel, AmbulanceType


class ConceptType(str, enum.Enum):
    EXPLICIT_CONDITION = "explicit_condition"
    SYMPTOM = "symptom"
    ACUITY_MARKER = "acuity_marker"
    VAGUE_DISTRESS = "vague_distress"


class EmergencyTypeStr(str):
    """
    Polymorphic emergency type string that cleanly equates canonical codes
    (e.g., 'CARDIAC', 'RESPIRATORY', 'STROKE', 'BURN', 'TRAUMA')
    with traditional title-case labels (e.g., 'Cardiac Emergency', 'Respiratory Emergency')
    while serializing cleanly as standard JSON string.
    """
    CANONICAL_SYNONYMS = {
        "CARDIAC": {
            "CARDIAC", "CARDIAC EMERGENCY", "HEART ATTACK", "CARDIAC ARREST", "CARDIAC_EMERGENCY"
        },
        "RESPIRATORY": {
            "RESPIRATORY", "RESPIRATORY EMERGENCY", "RESPIRATORY DISTRESS", "RESPIRATORY_EMERGENCY"
        },
        "STROKE": {
            "STROKE", "SUSPECTED STROKE", "BRAIN STROKE", "SUSPECTED_STROKE"
        },
        "BURN": {
            "BURN", "BURNS", "BURN INJURY", "BURN_INJURY", "FIRE & BURNS"
        },
        "BLEEDING": {
            "BLEEDING", "SEVERE BLEEDING", "SEVERE BLEEDING / TRAUMA", "SEVERE_BLEEDING"
        },
        "ROAD_TRAFFIC_ACCIDENT": {
            "ROAD TRAFFIC ACCIDENT", "ROAD_TRAFFIC_ACCIDENT", "ACCIDENT", "RTA", "VEHICLE COLLISION"
        },
        "TRAUMA": {
            "TRAUMA", "TRAUMA / FALL", "FALL", "TRAUMA_FALL", "SEVERE BLEEDING / TRAUMA"
        },
        "SEIZURE": {
            "SEIZURE", "SEIZURE / NEUROLOGICAL", "EPILEPSY", "CONVULSION"
        },
        "GENERAL_MEDICAL": {
            "GENERAL MEDICAL EMERGENCY", "GENERAL_MEDICAL", "GENERAL_MEDICAL_EMERGENCY",
            "GENERAL", "MEDICAL EMERGENCY", "GENERAL MEDICAL"
        },
        "PEDIATRIC": {
            "PEDIATRIC EMERGENCY", "PEDIATRIC", "PEDIATRIC_EMERGENCY"
        },
        "UNKNOWN": {
            "UNKNOWN", "UNCLEAR", "UNCLEAR/PENDING", "PENDING"
        },
    }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (str, bytes)):
            return False
        s_self = str(self).strip().upper()
        s_other = str(other).strip().upper()
        if s_self == s_other:
            return True
        for canonical, syns in self.CANONICAL_SYNONYMS.items():
            if s_self in syns and s_other in syns:
                return True
        return False

    def __hash__(self) -> int:
        s_self = str(self).strip().upper()
        for canonical, syns in self.CANONICAL_SYNONYMS.items():
            if s_self in syns:
                return hash(canonical)
        return hash(s_self)


class LanguageStr(str):
    """
    Polymorphic language string that cleanly equates ISO codes ('en', 'mr', 'hi')
    with full names ('English', 'Marathi', 'Hindi', 'Code-Mixed')
    while serializing cleanly as standard JSON string.
    """
    SYNONYMS = {
        "ENGLISH": {"ENGLISH", "EN", "EN-IN"},
        "MARATHI": {"MARATHI", "MR", "MR-IN"},
        "HINDI": {"HINDI", "HI", "HI-IN"},
        "CODE_MIXED": {
            "CODE-MIXED", "CODE_MIXED", "HINGLISH", "MARATHISH", "MR-EN", "HI-EN",
            "CODE-MIXED (HINGLISH)", "CODE-MIXED (MARATHI-ENGLISH)"
        },
    }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (str, bytes)):
            return False
        s1 = str(self).strip().upper()
        s2 = str(other).strip().upper()
        if s1 == s2:
            return True
        for syn_set in self.SYNONYMS.values():
            if s1 in syn_set and s2 in syn_set:
                return True
        return False

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            i = item.strip().upper()
            s = str(self).strip().upper()
            if i in s:
                return True
            for syn_set in self.SYNONYMS.values():
                if s in syn_set and any(i in syn for syn in syn_set):
                    return True
        return super().__contains__(item)

    def __hash__(self) -> int:
        s_self = str(self).strip().upper()
        for canonical, syns in self.SYNONYMS.items():
            if s_self in syns:
                return hash(canonical)
        return hash(s_self)



class NormalizedMedicalConcept(BaseModel):
    """Standardized clinical concept extracted from regional language expressions."""
    concept_id: str
    concept_type: ConceptType
    standardized_text: str
    category_hint: str
    severity_hint: SeverityLevel = SeverityLevel.MODERATE
    ambulance_hint: AmbulanceType = AmbulanceType.BLS
    matched_phrase: str
    language: str
    evidence: str


class NormalizationResult(BaseModel):
    """Comprehensive normalization outcome for an incoming emergency narrative."""
    detected_language: str
    language_code: str
    primary_category: str
    primary_concept: Optional[NormalizedMedicalConcept] = None
    all_concepts: List[NormalizedMedicalConcept] = Field(default_factory=list)
    normalized_medical_text: str = ""
    conscious_status: str = "unknown"
    breathing_status: str = "unknown"
    is_explicit_condition: bool = False
    has_life_threat: bool = False
    is_vague: bool = False
    evidence: List[str] = Field(default_factory=list)

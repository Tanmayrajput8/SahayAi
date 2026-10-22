"""
Core Medical Terminology Normalization Engine.

Translates regional language emergency phrases (Marathi, Hindi, Code-Mixed, English)
into standardized clinical concepts, evidence trails, and category determinations.
"""
import re
import logging
from typing import List, Optional, Tuple, Dict, Any

from app.models.case import SeverityLevel, AmbulanceType
from app.ai.normalization.schemas import (
    ConceptType,
    NormalizedMedicalConcept,
    NormalizationResult,
    EmergencyTypeStr,
)
from app.ai.normalization.dictionary import MEDICAL_TERMS_DB

logger = logging.getLogger(__name__)

# Marathi grammatical and vocabulary markers in Devanagari
MARATHI_MARKERS = [
    "आहे", "आहेत", "झाला", "झाली", "झाले", "होत", "होते", "येथे", "जवळ", "पडला",
    "पडली", "पडले", "पक्षाघात", "हृदयविकाराचा", "झटका", "छातीत", "दुखत", "श्वास",
    "घेता", "येत", "नाही", "बेशुद्ध", "शुद्धीवर", "रक्त", "वाहत", "भाजले", "जळाला",
    "धडक", "अपघात", "बरा", "वाटत", "तब्येत", "लवकर", "मदत", "त्याला", "तिला",
    "त्यांना", "रुग्णाला", "माणूस", "बाई", "मुलगा", "मुलगी", "होरपळला", "कळ",
    "दुखते", "सांगा", "पाठवा"
]

# Hindi grammatical and vocabulary markers in Devanagari
HINDI_MARKERS = [
    "है", "हैं", "हो", "रहा", "रही", "रहे", "हुआ", "हुई", "हुए", "था", "थी", "थे",
    "पड़ा", "पड़ी", "पड़े", "पास", "गिरा", "गिरी", "गिरे", "मरीज", "पिताजी", "माताजी",
    "भाई", "बहन", "आदमी", "औरत", "बच्चा", "बच्ची", "दर्द", "दौरा", "दिल", "सीने",
    "सांस", "तकलीफ", "बेहोश", "खून", "बह", "जल", "गया", "टक्कर", "दुर्घटना",
    "एक्सीडेंट", "भेजो", "मदद", "करो", "जल्दी", "बहुत"
]

from app.ai.normalization.schemas import (
    ConceptType,
    NormalizedMedicalConcept,
    NormalizationResult,
    EmergencyTypeStr,
    LanguageStr,
)

# Code-mixed phonetic markers (word-boundary regex to prevent false matches with English words)
MARATHISH_REGEX = [
    re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    for word in [
        "zala", "zali", "zale", "ahe", "ahet", "tras", "hot ahe", "chhati",
        "shwas", "madat", "kuthla", "yet nahi", "ghyayla", "bhajla", "padla",
        "madhe", "yethe", "khup", "bara vatat", "bare vatat"
    ]
]

HINGLISH_REGEX = [
    re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    for word in [
        "bhai", "jaldi", "ho gaya", "gayi", "bohot", "bahut", "nikal",
        "chahiye", "kar do", "dard", "saans", "khoon", "beh raha", "thuk gayi",
        "madad", "chhoot raha"
    ]
]


class MedicalNormalizer:
    """
    Production-grade multilingual clinical terminology normalization engine.
    Ensures that regional medical idioms are converted into authoritative clinical concepts.
    """

    @staticmethod
    def detect_language(text: str, hint: Optional[str] = None) -> Tuple[LanguageStr, str]:
        """
        Detects language from narrative text and optional caller hint.
        Returns Tuple of (Display Language Name as LanguageStr, ISO/BCP code).
        """
        if hint:
            h = hint.strip().lower()
            if h in ("marathi", "mr", "mr-in"):
                return LanguageStr("Marathi"), "mr"
            if h in ("hindi", "hi", "hi-in"):
                return LanguageStr("Hindi"), "hi"
            if h in ("english", "en", "en-in"):
                return LanguageStr("English"), "en"
            if "code" in h or "mixed" in h or "hinglish" in h or "marathish" in h:
                return LanguageStr("Code-Mixed"), "code-mixed"

        clean = text.strip()
        lower = clean.lower()

        # 1. Check Devanagari Script presence
        has_devanagari = bool(re.search(r"[\u0900-\u097F]", clean))
        if has_devanagari:
            marathi_score = sum(1 for m in MARATHI_MARKERS if m in clean)
            hindi_score = sum(1 for h in HINDI_MARKERS if h in clean)

            if marathi_score > hindi_score:
                return LanguageStr("Marathi"), "mr"
            elif hindi_score > marathi_score:
                return LanguageStr("Hindi"), "hi"
            else:
                # Disambiguate by specific verb endings
                if any(w in clean for w in ["आहे", "झाला", "येत नाही", "दुखत", "वाटत"]):
                    return LanguageStr("Marathi"), "mr"
                return LanguageStr("Hindi"), "hi"

        # 2. Check Romanized / Code-Mixed patterns
        marathish_score = sum(1 for r in MARATHISH_REGEX if r.search(lower))
        hinglish_score = sum(1 for r in HINGLISH_REGEX if r.search(lower))

        if marathish_score > 0 and marathish_score >= hinglish_score:
            return LanguageStr("Code-Mixed (Marathi-English)"), "mr-en"
        elif hinglish_score > 0:
            return LanguageStr("Code-Mixed (Hinglish)"), "hi-en"

        return LanguageStr("English"), "en"


    def normalize(self, raw_text: str, language_hint: Optional[str] = None) -> NormalizationResult:
        """
        Analyze narrative emergency text and extract standardized clinical concepts,
        identifying explicit conditions, symptoms, and acuity markers.
        """
        text = (raw_text or "").strip()
        lower = text.lower()
        lang_name, lang_code = self.detect_language(text, language_hint)

        matched_concepts: List[NormalizedMedicalConcept] = []
        evidence_list: List[str] = []

        # Determine language priority keys for pattern matching
        lookup_keys = []
        if lang_code == "mr":
            lookup_keys = ["mr", "code_mixed", "en", "hi"]
        elif lang_code == "hi":
            lookup_keys = ["hi", "code_mixed", "en", "mr"]
        elif lang_code in ("mr-en", "hi-en", "code-mixed"):
            lookup_keys = ["code_mixed", "en", "mr", "hi"]
        else:
            lookup_keys = ["en", "code_mixed", "hi", "mr"]

        for item in MEDICAL_TERMS_DB:
            concept_id = item["concept_id"]
            concept_type = item["concept_type"]
            std_text = item["standardized_text"]
            cat_hint = item["category_hint"]
            sev_hint = item["severity_hint"]
            amb_hint = item["ambulance_hint"]
            template = item.get("evidence_template", "{lang} phrase '{phrase}' identified")

            found_match = False
            best_matched_phrase = ""

            for key in lookup_keys:
                patterns = item.get("patterns", {}).get(key, [])
                for pattern in patterns:
                    # Check substring match (case-insensitive for Latin, exact for Devanagari)
                    if (pattern.lower() in lower) or (pattern in text):
                        found_match = True
                        best_matched_phrase = pattern
                        break
                if found_match:
                    break

            if found_match:
                evidence_str = template.format(lang=lang_name, phrase=best_matched_phrase)
                concept = NormalizedMedicalConcept(
                    concept_id=concept_id,
                    concept_type=concept_type,
                    standardized_text=std_text,
                    category_hint=cat_hint,
                    severity_hint=sev_hint,
                    ambulance_hint=amb_hint,
                    matched_phrase=best_matched_phrase,
                    language=lang_name,
                    evidence=evidence_str,
                )
                matched_concepts.append(concept)
                evidence_list.append(evidence_str)

        # ---------------------------------------------------------------------
        # Consciousness Status Extraction
        # ---------------------------------------------------------------------
        conscious_status = "unknown"
        if any(c.concept_id == "unconscious" for c in matched_concepts):
            conscious_status = "unconscious"
        elif any(w in lower or w in text for w in ["शुद्धीवर आहे", "होश में है", "conscious", "awake"]):
            conscious_status = "conscious"

        # ---------------------------------------------------------------------
        # Breathing Status Extraction
        # ---------------------------------------------------------------------
        breathing_status = "unknown"
        if any(c.concept_id == "stopped_breathing" for c in matched_concepts):
            breathing_status = "stopped"
        elif any(c.concept_id == "difficulty_breathing" for c in matched_concepts) or (
            ("श्वास" in text or "सांस" in text or "breath" in lower)
            and ("त्रास" in text or "तकलीफ" in text or "दिक्कत" in text or "problem" in lower or "difficult" in lower)
        ):
            breathing_status = "difficulty"
        elif any(w in lower or w in text for w in ["सांस चल रही", "श्वास चालू", "normal breathing"]):
            breathing_status = "normal"


        # ---------------------------------------------------------------------
        # Primary Category Determination
        # ---------------------------------------------------------------------
        # Hierarchical resolution:
        # 1. Explicit reported medical conditions (Heart attack, Stroke, Burn, Vehicle Crash)
        # 2. High acuity symptoms (Chest pain, Breathing distress, Severe bleeding)
        # 3. Non-vehicle fall/trauma
        # 4. Vague distress or unknown
        primary_category = "UNKNOWN"
        primary_concept: Optional[NormalizedMedicalConcept] = None
        is_explicit = False
        has_life_threat = False
        is_vague = False

        # Check explicit conditions first
        explicit_matches = [c for c in matched_concepts if c.concept_type == ConceptType.EXPLICIT_CONDITION]
        if explicit_matches:
            primary_concept = explicit_matches[0]
            primary_category = primary_concept.category_hint
            is_explicit = True
        else:
            # Check symptoms next
            symptom_matches = [c for c in matched_concepts if c.concept_type == ConceptType.SYMPTOM]
            if symptom_matches:
                primary_concept = symptom_matches[0]
                primary_category = primary_concept.category_hint
            else:
                # Check acuity markers (e.g. unconscious alone without named disease)
                acuity_matches = [c for c in matched_concepts if c.concept_type == ConceptType.ACUITY_MARKER]
                if acuity_matches:
                    primary_concept = acuity_matches[0]
                    # Unconscious without specific category is high acuity general medical
                    primary_category = "GENERAL_MEDICAL"
                else:
                    vague_matches = [c for c in matched_concepts if c.concept_type == ConceptType.VAGUE_DISTRESS]
                    if vague_matches:
                        primary_concept = vague_matches[0]
                        primary_category = "GENERAL_MEDICAL"
                        is_vague = True
                    else:
                        primary_category = "UNKNOWN"
                        is_vague = True

        # Check life-threat indicators
        if conscious_status == "unconscious" or breathing_status == "stopped":
            has_life_threat = True
        if primary_concept and primary_concept.concept_id in ("reported_heart_attack", "severe_bleeding"):
            has_life_threat = True

        # Build normalized summary text
        if matched_concepts:
            normalized_medical_text = "; ".join(c.standardized_text for c in matched_concepts)
        elif is_vague:
            normalized_medical_text = "vague medical complaint; clinical details insufficient"
        else:
            normalized_medical_text = "general distress narrative"

        return NormalizationResult(
            detected_language=lang_name,
            language_code=lang_code,
            primary_category=primary_category,
            primary_concept=primary_concept,
            all_concepts=matched_concepts,
            normalized_medical_text=normalized_medical_text,
            conscious_status=conscious_status,
            breathing_status=breathing_status,
            is_explicit_condition=is_explicit,
            has_life_threat=has_life_threat,
            is_vague=is_vague,
            evidence=evidence_list,
        )


# Global singleton instance
_normalizer = MedicalNormalizer()


def normalize_medical_text(raw_text: str, language_hint: Optional[str] = None) -> NormalizationResult:
    """Convenience helper to normalize regional language emergency text."""
    return _normalizer.normalize(raw_text=raw_text, language_hint=language_hint)

"""Mock LLM Provider for offline research prototype, CI testing, and deterministic evaluation."""
import re
import logging
from typing import Optional, Dict, Any, List

from app.ai.providers.grok import GrokProvider
from app.ai.schemas import EmergencyExtractionResult
from app.ai.exceptions import LLMTimeoutError, LLMAPIError, LLMOutputFormatError
from app.models.case import SeverityLevel, AmbulanceType

logger = logging.getLogger(__name__)


class MockProvider(GrokProvider):
    """
    Intelligent Mock LLM Provider with heuristic NLP rule-engine.
    Inherits from GrokProvider (and LLMProvider).
    Accurately simulates LLM responses for:
    - Multilingual emergency text (English, Hindi, Marathi, Code-Mixed)
    - Typos, abbreviations, slang, panic-style messages
    - Incomplete descriptions and missing info flagging
    - Contradiction detection
    - Simulated timeouts, API errors, and malformed JSON for failure testing
    """

    def __init__(
        self,
        api_key: str = "mock-key",
        api_url: str = "https://api.x.ai/v1/chat/completions",
        model: str = "grok-beta",
        timeout: float = 15.0,
        max_retries: int = 2,
        simulate_timeout: bool = False,
        simulate_api_error: bool = False,
        simulate_malformed_json: bool = False,
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            api_url=api_url,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.simulate_timeout = simulate_timeout
        self.simulate_api_error = simulate_api_error
        self.simulate_malformed_json = simulate_malformed_json

    @property
    def provider_name(self) -> str:
        return "mock"

    def extract_emergency_info(
        self,
        raw_text: str,
        modality: str = "text",
        context: Optional[Dict[str, Any]] = None,
    ) -> EmergencyExtractionResult:
        """Simulate LLM extraction with NLP heuristics and test error injections."""

        # 1. Error simulation hooks
        if self.simulate_timeout:
            raise LLMTimeoutError("Simulated LLM API request timed out after 15.0s.")

        if self.simulate_api_error:
            raise LLMAPIError("Simulated upstream LLM provider 503 Service Unavailable.")

        if self.simulate_malformed_json:
            raise LLMOutputFormatError("Simulated unparseable LLM output: <<BROKEN_JSON>>")

        text = raw_text.strip()
        lower = text.lower()

        # 2. Language Detection
        is_devanagari = bool(re.search(r"[\u0900-\u097F]", text))
        detected_language = "English"

        if is_devanagari:
            # Check Marathi markers vs Hindi markers
            marathi_markers = ["आहे", "झाला", "पडली", "जवळ", "त्रास", "बेशुद्ध", "अपघात", "रक्त", "लवकर"]
            hindi_markers = ["है", "हुआ", "रहा", "बह", "भेजो", "खून", "मदद", "गिर"]
            if any(m in text for m in marathi_markers):
                detected_language = "Marathi"
            elif any(m in text for m in hindi_markers):
                detected_language = "Hindi"
            else:
                detected_language = "Hindi / Marathi (Devanagari)"
        else:
            # Romanized markers
            marathish_markers = ["zala", "ahe", "baher", "madat", "kuthla"]
            hinglish_markers = ["bhai", "jaldi", "gayi", "bohot", "nikal", "pe", "chahiye", "ho gaya", "karo"]
            if any(m in lower for m in marathish_markers):
                detected_language = "Code-Mixed (Marathi-English)"
            elif any(m in lower for m in hinglish_markers):
                detected_language = "Code-Mixed (Hinglish)"
            elif any(slang in lower for slang in ["plzz", "hlp", "accidnt", "some1", "bleedin", "brdr"]):
                detected_language = "English (Slang/Typos)"

        # 3. Location Extraction
        known_locations = [
            "Marine Drive", "Nariman Point", "Dadar Station", "Dadar", "Andheri Station",
            "Andheri", "Kurla Signal", "Kurla", "Swargate", "Kothrud", "Bandra West",
            "Bandra", "Western Express Highway", "MG Road", "Station", "Signal", "Depot",
            "Shivajinagar", "FC Road", "Deccan", "Pune", "Mumbai",
        ]
        extracted_location: Optional[str] = None
        for loc in known_locations:
            if loc.lower() in lower:
                extracted_location = loc
                break

        # Check Devanagari location names
        if not extracted_location:
            if "अंधेरी" in text:
                extracted_location = "अंधेरी स्टेशन (Andheri Station)"
            elif "दादर" in text:
                extracted_location = "दादर स्टेशन (Dadar Station)"
            elif "कुर्ला" in text:
                extracted_location = "कुर्ला (Kurla)"

        # 4. Contradiction Detection
        is_contradictory = False
        contradiction_notes: Optional[str] = None
        if ("dead" in lower and "walking" in lower) or ("fine" in lower and "unconscious" in lower) or ("no injury" in lower and "bleeding" in lower):
            is_contradictory = True
            contradiction_notes = "Contradiction detected: caller reports mutually incompatible clinical states."

        # 5. Symptoms & Emergency Type Classification
        symptoms: List[str] = []
        missing_info: List[str] = []
        conscious_status = "unknown"
        breathing_status = "unknown"

        # Check consciousness
        if any(w in lower for w in ["unconscious", "fainted", "collapsed", "बेशुद्ध", "बेहोश"]):
            conscious_status = "unconscious"
            symptoms.append("loss of consciousness")
        elif "conscious" in lower:
            conscious_status = "conscious"

        # Check breathing
        if any(w in lower for w in ["not breathing", "stopped breathing", "choking"]):
            breathing_status = "stopped"
            symptoms.append("respiratory arrest")
        elif any(w in lower for w in ["difficulty breathing", "shortness of breath", "त्रास", "दम"]):
            breathing_status = "difficulty"
            symptoms.append("dyspnea")

        # Check bleeding
        if any(w in lower for w in ["bleeding", "bleedin", "bleding", "blood", "खून", "रक्त"]):
            symptoms.append("hemorrhage / active bleeding")

        # Determine Emergency Type
        if any(w in lower for w in ["cardiac", "chest pain", "heart", "छाती"]):
            emergency_type = "Cardiac Emergency"
            symptoms.append("acute chest pain")
        elif any(w in lower or w in text for w in ["accident", "accidnt", "acident", "collision", "crash", "slip", "अपघात", "दुर्घटना", "एक्सीडेंट", "टक्कर"]):
            emergency_type = "Road Traffic Accident"
            symptoms.append("trauma / impact injury")
        elif any(w in lower for w in ["burn", "fire", "आग"]):
            emergency_type = "Burn Injury"
            symptoms.append("thermal burn")
        elif any(w in lower for w in ["fall", "fell down", "गिर"]):
            emergency_type = "Trauma / Fall"
            symptoms.append("fall from standing")
        elif any(w in lower for w in ["stroke", "paralysis"]):
            emergency_type = "Suspected Stroke"
            symptoms.append("neurological deficit")
        else:
            emergency_type = "General Medical Emergency"

        if not symptoms:
            symptoms.append("reported distress")

        # 6. Patient Count
        patient_count = 1
        count_match = re.search(r"(\d+)\s*(people|persons|patients|victims|injured)", lower)
        if count_match:
            try:
                patient_count = max(1, int(count_match.group(1)))
            except ValueError:
                pass
        elif "two" in lower or "दो" in text or "दोन" in text:
            patient_count = 2

        # 7. Missing Information Audit
        if not extracted_location:
            missing_info.append("exact location / landmark")
        if conscious_status == "unknown":
            missing_info.append("patient consciousness")
        if breathing_status == "unknown":
            missing_info.append("breathing stability")

        # 8. Severity & Ambulance Recommendation
        is_panic = "!" in text or "help help" in lower or "hurry" in lower or text.isupper()

        if conscious_status == "unconscious" or breathing_status == "stopped" or emergency_type == "Cardiac Emergency":
            severity = SeverityLevel.CRITICAL
            ambulance = AmbulanceType.ALS
            rationale = "Immediate life-threat (cardiac, unconsciousness, or respiratory failure) requires ALS ambulance."
        elif "severe" in lower or emergency_type == "Road Traffic Accident" or breathing_status == "difficulty":
            severity = SeverityLevel.HIGH
            ambulance = AmbulanceType.ALS
            rationale = "High acuity event with risk of rapid deterioration. ALS ambulance recommended."
        elif emergency_type in ("Trauma / Fall", "General Medical Emergency") and len(missing_info) <= 1:
            severity = SeverityLevel.MODERATE
            ambulance = AmbulanceType.BLS
            rationale = "Moderate acuity situation without immediate airway or hemodynamic compromise. BLS assigned."
        else:
            severity = SeverityLevel.MODERATE
            ambulance = AmbulanceType.BLS
            rationale = "Initial triage assigned BLS based on available caller narrative."

        if is_panic:
            rationale += " High caller panic indicators detected in input."

        # Confidence Scoring
        confidence = 0.88
        if not extracted_location:
            confidence -= 0.15
        if len(missing_info) >= 2:
            confidence -= 0.15
        if is_contradictory:
            confidence -= 0.35

        confidence = max(0.2, min(0.98, confidence))

        return EmergencyExtractionResult(
            emergency_type=emergency_type,
            symptoms=symptoms,
            location=extracted_location,
            severity=severity,
            patient_count=patient_count,
            detected_language=detected_language,
            ambulance_requirement=ambulance,
            missing_information=missing_info,
            conscious_status=conscious_status,
            breathing_status=breathing_status,
            clinical_rationale=rationale,
            confidence_score=round(confidence, 2),
            is_contradictory=is_contradictory,
            contradiction_notes=contradiction_notes,
        )

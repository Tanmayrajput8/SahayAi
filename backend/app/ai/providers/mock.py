"""Mock LLM Provider for offline research prototype, CI testing, and deterministic evaluation."""
import re
import logging
from typing import Optional, Dict, Any, List

from app.ai.providers.grok import GrokProvider
from app.ai.schemas import EmergencyExtractionResult
from app.ai.exceptions import LLMTimeoutError, LLMAPIError, LLMOutputFormatError
from app.models.case import SeverityLevel, AmbulanceType
from app.ai.normalization import normalize_medical_text


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

        # 2. Medical Terminology Normalization & Language Detection
        norm = normalize_medical_text(text, language_hint=context.get("language_hint") if context else None)
        detected_language = norm.detected_language

        # 3. Location Extraction
        known_locations = [
            "Marine Drive", "Nariman Point", "Dadar Station", "Dadar", "Andheri Station",
            "Andheri", "Kurla Signal", "Kurla", "Swargate", "Kothrud", "Bandra West",
            "Bandra", "Western Express Highway", "MG Road", "Station", "Signal", "Depot",
            "Shivajinagar", "FC Road", "Deccan", "Pune", "Mumbai", "Katraj", "Hadapsar",
            "Dhankawadi", "Hinjewadi", "Aundh", "Baner"
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
            elif "कोथरूड" in text:
                extracted_location = "कोथरूड (Kothrud)"
            elif "स्वारगेट" in text:
                extracted_location = "स्वारगेट (Swargate)"
            elif "डेक्कन" in text:
                extracted_location = "डेक्कन (Deccan)"
            elif "शिवाजीनगर" in text:
                extracted_location = "शिवाजीनगर (Shivajinagar)"
            elif "हडपसर" in text:
                extracted_location = "हडपसर (Hadapsar)"
            elif "कात्रज" in text:
                extracted_location = "कात्रज (Katraj)"

        # 4. Contradiction Detection
        is_contradictory = False
        contradiction_notes: Optional[str] = None
        if ("dead" in lower and "walking" in lower) or ("fine" in lower and "unconscious" in lower) or ("no injury" in lower and "bleeding" in lower):
            is_contradictory = True
            contradiction_notes = "Contradiction detected: caller reports mutually incompatible clinical states."

        # 5. Symptoms & Emergency Type Classification using Medical Normalization
        symptoms: List[str] = []
        missing_info: List[str] = []
        conscious_status = norm.conscious_status
        breathing_status = norm.breathing_status

        # Collect clinical concepts into symptoms
        for c in norm.all_concepts:
            if c.standardized_text not in symptoms:
                symptoms.append(c.standardized_text)

        # Primary Emergency Type Mapping
        from app.ai.normalization.schemas import EmergencyTypeStr

        if norm.primary_category == "CARDIAC":
            emergency_type = EmergencyTypeStr("Cardiac Emergency")
            if "acute chest pain" not in symptoms and "reported heart attack" not in symptoms:
                symptoms.append("acute chest pain")
        elif norm.primary_category == "STROKE":
            emergency_type = EmergencyTypeStr("Suspected Stroke")
            if "neurological deficit" not in symptoms:
                symptoms.append("neurological deficit")
        elif norm.primary_category == "BURN":
            emergency_type = EmergencyTypeStr("Burn Injury")
            if "thermal burn" not in symptoms:
                symptoms.append("thermal burn")
        elif norm.primary_category == "RESPIRATORY":
            emergency_type = EmergencyTypeStr("Respiratory Emergency")
            if "breathing difficulty" not in symptoms:
                symptoms.append("breathing difficulty")
        elif norm.primary_category == "BLEEDING":
            emergency_type = EmergencyTypeStr("Severe Bleeding / Trauma")
            if "severe hemorrhage" not in symptoms:
                symptoms.append("severe hemorrhage")
        elif norm.primary_category == "ROAD_TRAFFIC_ACCIDENT":
            emergency_type = EmergencyTypeStr("Road Traffic Accident")
            if "trauma / impact injury" not in symptoms:
                symptoms.append("trauma / impact injury")
        elif norm.primary_category == "TRAUMA":
            emergency_type = EmergencyTypeStr("Trauma / Fall")
            if "fall injury" not in symptoms:
                symptoms.append("fall injury")
        elif norm.is_vague:
            emergency_type = EmergencyTypeStr("General Medical Emergency")
            if "reported distress" not in symptoms:
                symptoms.append("reported distress")
        else:
            emergency_type = EmergencyTypeStr("General Medical Emergency")
            if not symptoms:
                symptoms.append("reported distress")

        # Check typos and slang for prototype test resilience
        if "accidnt" in lower or "acident" in lower:
            emergency_type = EmergencyTypeStr("Road Traffic Accident")
            if "trauma / impact injury" not in symptoms:
                symptoms.append("trauma / impact injury")
        if "bleedin" in lower or "bleed" in lower:
            if not any("bleeding" in s or "hemorrhage" in s for s in symptoms):
                symptoms.append("active bleeding / hemorrhage")

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
            rationale = "Immediate life-threat (cardiac, unconsciousness, or respiratory arrest) requires ALS ambulance."
        elif norm.is_vague:
            severity = SeverityLevel.UNKNOWN
            ambulance = AmbulanceType.UNKNOWN
            rationale = "Clinical information in caller narrative is vague or insufficient for automated dispatch. Mandatory dispatcher review required."
        elif "severe" in lower or emergency_type in ("Road Traffic Accident", "Respiratory Emergency", "Burn Injury", "Severe Bleeding / Trauma", "Suspected Stroke") or breathing_status == "difficulty":
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
        if norm.is_vague:
            confidence = 0.50
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
            evidence=list(norm.evidence),
            normalized_medical_text=norm.normalized_medical_text,
        )

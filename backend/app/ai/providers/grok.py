"""Groq Cloud / OpenAI-compatible REST API Provider Implementation."""
import logging
import time
from typing import Optional, Dict, Any, List
import httpx

from app.ai.providers.base import LLMProvider
from app.ai.schemas import EmergencyExtractionResult
from app.ai.exceptions import LLMTimeoutError, LLMAPIError, LLMOutputFormatError
from app.ai.json_utils import parse_and_validate_extraction
from app.ai.normalization import normalize_medical_text
from app.ai.normalization.schemas import EmergencyTypeStr
from app.models.case import SeverityLevel, AmbulanceType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are SahayAI's clinical triage intelligence layer for emergency ambulance dispatch (Research Prototype).\n"
    "Your role is to analyze raw emergency text transcripts from callers/citizens along with normalized clinical concepts and extract structured triage intelligence.\n"
    "\n"
    "Instructions:\n"
    "1. Support multi-lingual input: English, Hindi, Marathi, and Code-Mixed (Hinglish, Marathish), as well as typos, slang, and panic-style phrasing.\n"
    "2. DO NOT reject or fail simply because information is incomplete. Identify missing details in the 'missing_information' array.\n"
    "3. Classify clinical severity into exactly one of: CRITICAL, HIGH, MODERATE, LOW.\n"
    "   - CRITICAL: Cardiac arrest, unconsciousness, severe hemorrhage, major airway obstruction, multiple severe casualties. Requires ALS ambulance.\n"
    "   - HIGH: Suspected fracture with severe pain, moderate bleeding, respiratory distress, severe burns. Requires ALS or BLS.\n"
    "   - MODERATE: Minor fractures, manageable pain, stable vitals, mild asthma. Requires BLS.\n"
    "   - LOW: Non-life-threatening, minor scrapes, cold, chronic symptoms. Requires BLS.\n"
    "4. Classify ambulance requirement into: ALS (Advanced Life Support) or BLS (Basic Life Support).\n"
    "5. Extract mentioned landmark/location if present. If absent, set location to null and include in missing_information.\n"
    "6. Check for contradictory statements (e.g. patient is dead but walking fine). If contradictory, set is_contradictory=true and reduce confidence_score.\n"
    "7. CRITICAL CLASSIFICATION RULE for emergency_type. Choose the MOST ACCURATE specific category:\n"
    "   - Cardiac Emergency / CARDIAC: chest pain, heart attack, cardiac arrest, palpitations, seeney mein dard, dil ka daura (दिल का दौरा), हृदयविकाराचा झटका, छातीत दुखणे, छातीत प्रचंड कळ\n"
    "   - Suspected Stroke / STROKE: facial drooping, slurred speech, arm weakness, sudden confusion, paralysis, पक्षाघात, लकवा\n"
    "   - Burn Injury / BURN: burns, fire injury, scalding, chemical burn, aag se jalana, जल गया है, भाजले आहे, आगीत होरपळला\n"
    "   - Respiratory Emergency / RESPIRATORY: difficulty breathing, asthma attack, choking, breathlessness, saans lene me dikkat, सांस लेने में तकलीफ, श्वास घेता येत नाही, दम लागत आहे\n"
    "   - Severe Bleeding / Trauma / BLEEDING: heavy or uncontrolled hemorrhage, बहुत खून बह रहा है, खूप रक्त वाहत आहे\n"
    "   - Road Traffic Accident / ROAD_TRAFFIC_ACCIDENT: ONLY when explicit vehicle collision is mentioned (car/bike/truck crash, road accident, gadi ki takkar, वाहनाची धडक, अपघात झाला)\n"
    "   - Trauma / Fall / TRAUMA: falls without vehicle involvement, slipping, sports injury, सीढ़ियों से गिर गया, पाय घसरून पडले\n"
    "   - Seizure / Neurological / SEIZURE: seizure, convulsion, epilepsy, unresponsive with shaking, मिर्गी, झटका\n"
    "   - General Medical Emergency / GENERAL_MEDICAL: non-specific distress, vague illness, or unclear emergency.\n"
    "   IMPORTANT RULES:\n"
    "   - NEVER use General Medical Emergency as a default for non-English inputs when specific medical expressions exist.\n"
    "   - NEVER default to Road Traffic Accident unless a vehicle collision is EXPLICITLY described.\n"
    "   - Distinguish symptoms from diagnoses: 'छातीत दुखत आहे' is chest pain (possible cardiac); 'हृदयविकाराचा झटका' is reported heart attack (CARDIAC).\n"
    "   - DO NOT invent facts: If caller did not state consciousness, set conscious_status to 'unknown'. If caller did not state breathing, set breathing_status to 'unknown'.\n"
    "8. Return ONLY strict, valid JSON with no markdown fences or extra text:\n"
    '{"emergency_type": "CARDIAC", "symptoms": ["acute chest pain"], "location": "Dadar Station East" or null, '
    '"severity": "CRITICAL", "patient_count": 1, "detected_language": "Marathi", "ambulance_requirement": "ALS", '
    '"missing_information": ["exact landmark"], "conscious_status": "unknown", "breathing_status": "unknown", '
    '"clinical_rationale": "Reported heart attack is life-threatening cardiac event requiring ALS ambulance.", '
    '"confidence_score": 0.90, "is_contradictory": false, "contradiction_notes": null, '
    '"evidence": ["Marathi phrase \'हृदयविकाराचा झटका\' corresponds to reported heart attack"]}'
)


class GroqProvider(LLMProvider):
    """
    Direct REST API client for Groq Cloud and OpenAI-compatible models (e.g. Llama 3.3, Qwen 3.8).
    Does not rely on third-party SDKs; communicates via httpx with built-in retries,
    timeout handling, and malformed-output recovery.
    """

    FALLBACK_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"]

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.groq.com/openai/v1/chat/completions",
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 20.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return "groq"

    def _call_groq_api(self, prompt: str, model_override: Optional[str] = None) -> str:
        """Execute HTTP POST request to Groq REST API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        current_model = model_override or self.model
        payload = {
            "model": current_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.api_url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Groq API timed out after {self.timeout}s") from exc
        except httpx.RequestError as exc:
            raise LLMAPIError(f"Network error communicating with Groq API: {exc}") from exc

        # Handle model not found (404) by falling back to alternative active models on Groq
        if response.status_code == 404 and "model_not_found" in response.text:
            for fallback_model in self.FALLBACK_MODELS:
                if fallback_model != current_model:
                    logger.info("Model '%s' not found. Retrying with active Groq fallback model '%s'.", current_model, fallback_model)
                    payload["model"] = fallback_model
                    try:
                        with httpx.Client(timeout=self.timeout) as client:
                            response = client.post(self.api_url, headers=headers, json=payload)
                        if response.status_code == 200:
                            self.model = fallback_model  # update active model
                            break
                    except Exception:
                        continue

        if response.status_code != 200:
            raise LLMAPIError(
                f"Groq API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            # Some reasoning models put the text in reasoning if content is empty
            if not content.strip() and "reasoning" in message:
                content = message["reasoning"]
            return content
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMOutputFormatError(f"Unexpected API response payload: {exc}") from exc

    def extract_emergency_info(
        self,
        raw_text: str,
        modality: str = "text",
        context: Optional[Dict[str, Any]] = None,
    ) -> EmergencyExtractionResult:
        """
        Extract structured emergency details with medical terminology normalization,
        retry logic, and malformed-output recovery.
        """
        # 1. Normalize medical terminology and extract regional language concepts
        norm = normalize_medical_text(raw_text)

        evidence_section = "\n".join(f"- {e}" for e in norm.evidence) if norm.evidence else "None"
        user_prompt = (
            f"Modality: {modality}\n"
            f"Caller Emergency Description (Original):\n\"\"\"{raw_text}\"\"\"\n\n"
            f"Normalized Clinical Interpretation:\n"
            f"- Detected Language: {norm.detected_language} ({norm.language_code})\n"
            f"- Normalized Clinical Concepts: {norm.normalized_medical_text}\n"
            f"- Clinical Category Suggestion: {norm.primary_category}\n"
            f"- Clinical Evidence:\n{evidence_section}\n\n"
            f"Produce the strict JSON emergency extraction according to instructions. "
            f"Ensure 'emergency_type' reflects the specific medical concept, not a generic fallback."
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                raw_response = self._call_groq_api(user_prompt)
                result = parse_and_validate_extraction(raw_response)

                # Ensure evidence is grounded
                if not result.evidence and norm.evidence:
                    result.evidence = list(norm.evidence)
                if not result.normalized_medical_text and norm.normalized_medical_text:
                    result.normalized_medical_text = norm.normalized_medical_text

                # Overwrite generic fallback if explicit medical condition was detected
                if norm.is_explicit_condition and result.emergency_type in ("General Medical Emergency", "Unknown", "GENERAL_MEDICAL"):
                    result.emergency_type = EmergencyTypeStr(norm.primary_category)
                    if norm.has_life_threat:
                        result.severity = SeverityLevel.CRITICAL
                        result.ambulance_requirement = AmbulanceType.ALS

                # Do not hallucinate unknown consciousness or breathing
                if norm.conscious_status == "unknown" and result.conscious_status not in ("conscious", "unconscious"):
                    result.conscious_status = "unknown"
                if norm.breathing_status == "unknown" and result.breathing_status not in ("normal", "difficulty", "stopped"):
                    result.breathing_status = "unknown"

                return result

            except LLMOutputFormatError as exc:
                logger.warning(
                    "Groq output format error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                last_error = exc
                if attempt < self.max_retries:
                    user_prompt = (
                        f"Your previous response could not be parsed as valid JSON.\n"
                        f"Error: {exc}\n"
                        f"Original text: \"\"\"{raw_text}\"\"\"\n"
                        f"Return ONLY the strict JSON object with no other text."
                    )
                    time.sleep(0.5)

            except (LLMTimeoutError, LLMAPIError) as exc:
                logger.warning(
                    "Groq API error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))

        # If all retries exhausted, raise last error so caller can route to human review
        raise last_error or LLMAPIError("Groq extraction failed after retries.")


class GrokProvider(GroqProvider):
    """Backwards-compatibility subclass alias for GroqProvider."""
    @property
    def provider_name(self) -> str:
        return "grok"


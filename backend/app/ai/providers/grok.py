"""Grok / xAI REST API Provider Implementation without OpenAI SDK."""
import logging
import time
from typing import Optional, Dict, Any
import httpx

from app.ai.providers.base import LLMProvider
from app.ai.schemas import EmergencyExtractionResult
from app.ai.exceptions import LLMTimeoutError, LLMAPIError, LLMOutputFormatError
from app.ai.json_utils import parse_and_validate_extraction

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are SahayAI's clinical triage intelligence layer for emergency ambulance dispatch (Research Prototype).
Your role is to analyze raw emergency text transcripts from callers/citizens and extract structured triage intelligence.

Instructions:
1. Support multi-lingual input: English, Hindi, Marathi, and Code-Mixed (Hinglish, Marathish), as well as typos, slang, and panic-style phrasing.
2. DO NOT reject or fail simply because information is incomplete. Identify missing details in the 'missing_information' array.
3. Classify clinical severity into exactly one of: CRITICAL, HIGH, MODERATE, LOW.
   - CRITICAL: Cardiac arrest, unconsciousness, severe hemorrhage, major airway obstruction, multiple severe casualties. Requires ALS ambulance.
   - HIGH: Suspected fracture with severe pain, moderate bleeding, respiratory distress, severe burns. Requires ALS or BLS.
   - MODERATE: Minor fractures, manageable pain, stable vitals, mild asthma. Requires BLS.
   - LOW: Non-life-threatening, minor scrapes, cold, chronic symptoms. Requires BLS.
4. Classify ambulance requirement into: ALS (Advanced Life Support) or BLS (Basic Life Support).
5. Extract mentioned landmark/location if present. If absent, set location to null and include in missing_information.
6. Check for contradictory statements (e.g. "patient is dead but walking fine"). If contradictory, flag is_contradictory=true and drop confidence_score.
7. Return ONLY strict, valid JSON matching this exact structure:
{
  "emergency_type": "Road Traffic Accident | Cardiac Emergency | Trauma | Burns | etc.",
  "symptoms": ["chest pain", "shortness of breath"],
  "location": "Dadar Station East" or null,
  "severity": "CRITICAL" | "HIGH" | "MODERATE" | "LOW",
  "patient_count": 1,
  "detected_language": "English | Hindi | Marathi | Code-Mixed",
  "ambulance_requirement": "ALS" | "BLS",
  "missing_information": ["exact landmark", "patient consciousness"],
  "conscious_status": "conscious" | "unconscious" | "semi-conscious" | "unknown",
  "breathing_status": "normal" | "difficulty" | "gasping" | "stopped" | "unknown",
  "clinical_rationale": "Clear rationale explaining severity and ambulance selection.",
  "confidence_score": 0.85,
  "is_contradictory": false,
  "contradiction_notes": null
}
Output STRICT JSON ONLY. No markdown fences, no conversational preface.
"""


class GrokProvider(LLMProvider):
    """
    Direct REST API client for Grok / xAI models.
    Does not use the OpenAI SDK. Communicates via httpx with built-in retries,
    timeout handling, and malformed-output recovery.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.x.ai/v1/chat/completions",
        model: str = "grok-beta",
        timeout: float = 15.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def provider_name(self) -> str:
        return "grok"

    def _call_grok_api(self, prompt: str) -> str:
        """Execute HTTP POST request to Grok REST API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
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
            raise LLMTimeoutError(f"Grok API timed out after {self.timeout}s") from exc
        except httpx.RequestError as exc:
            raise LLMAPIError(f"Network error communicating with Grok API: {exc}") from exc

        if response.status_code != 200:
            raise LLMAPIError(
                f"Grok API returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMOutputFormatError(f"Unexpected API response payload: {exc}") from exc

    def extract_emergency_info(
        self,
        raw_text: str,
        modality: str = "text",
        context: Optional[Dict[str, Any]] = None,
    ) -> EmergencyExtractionResult:
        """Extract structured emergency details with retry and malformed-output recovery."""
        user_prompt = (
            f"Modality: {modality}\n"
            f"Caller Emergency Description:\n\"\"\"{raw_text}\"\"\"\n\n"
            f"Produce the strict JSON emergency extraction according to instructions."
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                raw_response = self._call_grok_api(user_prompt)
                return parse_and_validate_extraction(raw_response)

            except LLMOutputFormatError as exc:
                logger.warning(
                    "Grok output format error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                last_error = exc
                if attempt < self.max_retries:
                    # Provide an immediate recovery repair prompt for next attempt
                    user_prompt = (
                        f"Your previous response could not be parsed as valid JSON.\n"
                        f"Error: {exc}\n"
                        f"Original text: \"\"\"{raw_text}\"\"\"\n"
                        f"Return ONLY the strict JSON object with no other text."
                    )
                    time.sleep(0.5)

            except (LLMTimeoutError, LLMAPIError) as exc:
                logger.warning(
                    "Grok API error on attempt %d/%d: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))

        # If all retries exhausted, raise last error so caller can route to human review
        raise last_error or LLMAPIError("Grok extraction failed after retries.")

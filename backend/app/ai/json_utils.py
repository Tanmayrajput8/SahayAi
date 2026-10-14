"""JSON extraction, sanitization, and recovery utilities for LLM outputs."""
import ast
import json
import re
import logging
from typing import Dict, Any, Optional

from app.ai.exceptions import LLMOutputFormatError
from app.ai.schemas import EmergencyExtractionResult

logger = logging.getLogger(__name__)


def clean_json_string(text: str) -> str:
    """Strip markdown code blocks and surrounding whitespace."""
    text = text.strip()
    # Check for markdown code fence inside text
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    # Strip leading/trailing ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_outermost_json(text: str) -> Optional[str]:
    """Extract outermost {...} bracketed JSON substring."""
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]
    return None


def repair_json_syntax(json_str: str) -> str:
    """
    Repair common LLM JSON syntax anomalies:
    - JavaScript comments (// and /* */)
    - Trailing commas before closing braces/brackets
    - Python literals (None, True, False -> null, true, false)
    - Single quoted dictionary keys
    """
    # Remove single-line and multi-line comments
    repaired = re.sub(r"//.*$", "", json_str, flags=re.MULTILINE)
    repaired = re.sub(r"/\*[\s\S]*?\*/", "", repaired)

    # Remove trailing commas before closing brackets/braces
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)

    # Convert Python literals to standard JSON literals
    repaired = re.sub(r":\s*None\b", ": null", repaired)
    repaired = re.sub(r":\s*True\b", ": true", repaired)
    repaired = re.sub(r":\s*False\b", ": false", repaired)

    # Replace single-quoted dictionary keys: 'key': -> "key":
    repaired = re.sub(r"([{,]\s*)'([^']+)'\s*:", r'\1"\2":', repaired)

    return repaired.strip()


def parse_and_validate_extraction(raw_response: str) -> EmergencyExtractionResult:
    """
    Parse a raw string response from an LLM into an EmergencyExtractionResult.
    Applies multi-stage sanitization and recovery:
    1. Clean markdown code fences
    2. Direct JSON parse
    3. Regex extraction of outermost { ... }
    4. Syntax repair (trailing commas, comments, python literals, key quotes)
    5. Python AST literal evaluation fallback (for Python-dict formatted outputs)
    6. Pydantic validation
    Raises LLMOutputFormatError if unrecoverable.
    """
    cleaned = clean_json_string(raw_response)

    # Stage 1: Direct JSON parsing
    parsed_dict: Optional[Dict[str, Any]] = None
    try:
        parsed_dict = json.loads(cleaned)
    except Exception:
        pass

    # Stage 2: Extract outermost JSON object
    if parsed_dict is None:
        outer = extract_outermost_json(cleaned)
        if outer:
            try:
                parsed_dict = json.loads(outer)
            except Exception:
                # Stage 3: Repair syntax (e.g. trailing commas, python literals)
                repaired = repair_json_syntax(outer)
                try:
                    parsed_dict = json.loads(repaired)
                except Exception as exc:
                    logger.debug("Failed to recover JSON after syntax repair: %s", exc)

    # Stage 4: Try repair on cleaned string directly if outer was none or failed
    if parsed_dict is None:
        repaired_clean = repair_json_syntax(cleaned)
        try:
            parsed_dict = json.loads(repaired_clean)
        except Exception:
            pass

    # Stage 5: AST literal_eval fallback (for Python dictionary representation)
    if parsed_dict is None:
        outer = extract_outermost_json(cleaned) or cleaned
        try:
            candidate = ast.literal_eval(outer)
            if isinstance(candidate, dict):
                parsed_dict = candidate
        except Exception:
            pass

    if parsed_dict is None:
        raise LLMOutputFormatError(
            f"Could not parse valid JSON from LLM output. Raw snippet: {raw_response[:200]!r}"
        )

    # Stage 6: Pydantic Schema Validation
    try:
        return EmergencyExtractionResult.model_validate(parsed_dict)
    except Exception as exc:
        raise LLMOutputFormatError(
            f"LLM output failed Pydantic schema validation: {exc}"
        ) from exc

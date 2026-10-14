"""Abstract Base Class for LLM providers."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from app.ai.schemas import EmergencyExtractionResult


class LLMProvider(ABC):
    """
    Abstract Base Class for all LLM providers in SahayAI Emergency.
    All business logic interacts strictly through this abstraction.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier of the provider (e.g. 'grok', 'mock')."""
        pass

    @abstractmethod
    def extract_emergency_info(
        self,
        raw_text: str,
        modality: str = "text",
        context: Optional[Dict[str, Any]] = None,
    ) -> EmergencyExtractionResult:
        """
        Analyze emergency input and return a validated EmergencyExtractionResult.
        Must handle retries, timeouts, and raise appropriate LLM exceptions.
        """
        pass

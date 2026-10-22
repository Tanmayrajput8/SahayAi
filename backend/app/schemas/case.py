from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.models.case import CaseStatus, SeverityLevel, InputModality
from app.schemas.resource import AmbulanceResponse, HospitalResponse


class CaseCreate(BaseModel):
    """
    Schema for incoming citizen/caller emergency reports.
    Supports English, Hindi, Marathi, code-mixed, typos, slang, panic, and incomplete inputs.
    Text is the primary initial input, with architecture ready for voice/audio streams.
    """
    raw_input: Optional[str] = Field(
        default=None,
        description="Raw emergency text or description from citizen/caller",
        examples=["Accident near Dadar station, two bikes collided, need ambulance urgently"],
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Alias for raw_input to support alternate naming conventions",
    )
    modality: InputModality = Field(
        default=InputModality.TEXT,
        description="Modality of incoming emergency report: 'text', 'voice', or 'audio'",
    )
    caller_phone: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Optional caller callback phone number",
    )
    audio_url: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Audio recording URL for voice/audio modality",
    )
    language: Optional[str] = Field(
        default="unknown",
        max_length=32,
        description="Caller specified language hint or 'unknown'",
    )
    manual_location: Optional[str] = Field(
        default=None,
        max_length=256,
        description="Optional manual landmark or address provided by caller",
    )
    latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Optional GPS latitude from device/browser geolocation",
    )
    longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Optional GPS longitude from device/browser geolocation",
    )

    @model_validator(mode="after")
    def validate_and_normalize_input(self) -> "CaseCreate":
        # Resolve raw_input vs raw_text
        text = (self.raw_input or self.raw_text or "").strip()

        # Text modality requires non-empty description
        if self.modality == InputModality.TEXT:
            if not text:
                raise ValueError("Emergency description cannot be empty for text modality.")

        # Voice/Audio modality requires either a text transcript or an audio recording URL
        elif self.modality in (InputModality.VOICE, InputModality.AUDIO):
            if not text and not self.audio_url:
                raise ValueError("Either audio transcript (raw_input) or audio_url is required for voice/audio emergency.")

        # Normalize both fields so backend/consumers can use either interchangeably
        if text:
            self.raw_input = text
            self.raw_text = text
        elif not self.raw_text and self.audio_url:
            self.raw_input = f"[Audio stream/recording received: {self.audio_url}]"
            self.raw_text = self.raw_input

        return self


class CaseResponse(BaseModel):
    """Schema returned upon successful emergency case creation/retrieval."""
    id: str
    raw_input: str
    raw_text: str
    modality: str
    caller_phone: Optional[str] = None
    audio_url: Optional[str] = None
    language: str
    status: CaseStatus
    priority: SeverityLevel
    created_at: datetime
    updated_at: datetime
    message: str = "Emergency case successfully registered and queued for AI triage."

    model_config = ConfigDict(from_attributes=True)


class DuplicateSignalBreakdown(BaseModel):
    """Real calculated multi-signal duplicate detection details for staff inspection."""
    status: str = "NOT_DUPLICATE"
    score: float = 0.0
    matched_case_id: Optional[str] = None
    semantic_similarity: float = 0.0
    geographic_distance_km: Optional[float] = None
    location_similarity: float = 0.0
    temporal_diff_minutes: float = 0.0
    temporal_similarity: float = 0.0
    emergency_type_similarity: float = 0.0
    detection_method: str = "WEIGHTED_MULTISIGNAL"
    formula: str = "0.40*semantic + 0.30*location + 0.15*temporal + 0.15*type"
    requires_review: bool = False
    policy_notes: Optional[str] = None
    is_confirmed_duplicate: bool = False


class CaseTriageResponse(BaseModel):
    """Rich schema returned after AI extraction and clinical triage."""
    id: str
    status: CaseStatus
    priority: SeverityLevel
    detected_language: str
    raw_text: Optional[str] = None
    raw_input: Optional[str] = None
    caller_phone: Optional[str] = None
    language: Optional[str] = None
    modality: Optional[str] = None
    emergency_type: Optional[str] = None
    symptoms: list[str] = []
    extracted_location: Optional[str] = None
    patient_count: int = 1
    conscious_status: Optional[str] = "unknown"
    breathing_status: Optional[str] = "unknown"
    recommended_ambulance: Optional[str] = None
    clinical_rationale: Optional[str] = None
    confidence_score: float = 0.0
    missing_information: list[str] = []
    is_contradictory: bool = False
    routed_to_human_review: bool = False
    human_review_reason: Optional[str] = None
    extraction_status: str = "SUCCESS"  # SUCCESS or FAILED
    ai_suggested_severity: Optional[str] = None
    ai_suggested_ambulance: Optional[str] = None
    deterministic_severity: Optional[str] = None
    deterministic_ambulance: Optional[str] = None
    has_conflict: bool = False
    conflict_reason: Optional[str] = None
    disclaimer: str = "PROTOTYPE DECISION-SUPPORT HEURISTIC: Not clinically validated triage. Requires human dispatcher verification."
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geocoding_status: Optional[str] = None
    geocoding_provider: Optional[str] = None
    is_location_verified: bool = False
    location_error: Optional[str] = None
    # Real dispatch assignment fields (from actual verified resource match)
    assigned_ambulance: Optional[AmbulanceResponse] = None
    assigned_hospital: Optional[HospitalResponse] = None
    eta_minutes: Optional[float] = None
    ambulance_distance_km: Optional[float] = None
    hospital_distance_km: Optional[float] = None
    duplicate_detection: Optional[DuplicateSignalBreakdown] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseLocationUpdate(BaseModel):
    """Schema for dispatcher manual location override / verification."""
    latitude: float = Field(..., description="Latitude coordinate", ge=-90.0, le=90.0)
    longitude: float = Field(..., description="Longitude coordinate", ge=-180.0, le=180.0)
    formatted_address: Optional[str] = Field(default=None, description="Dispatcher verified address / landmark")
    dispatcher_notes: Optional[str] = Field(default=None, description="Notes on why location was edited/verified")


from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.incident import SeverityLevel, AmbulanceType, IncidentStatus


class IncidentCreate(BaseModel):
    raw_text: str = Field(..., description="Emergency text transcript or description from caller")
    caller_phone: Optional[str] = Field(default=None, description="Caller callback phone number")
    audio_url: Optional[str] = Field(default=None, description="Optional audio recording URL")
    manual_location: Optional[str] = Field(default=None, description="Manually provided landmark or address")


class IncidentResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    caller_phone: Optional[str] = None
    raw_text: str
    detected_language: str
    emergency_type: Optional[str] = None
    symptoms: List[str] = []
    extracted_location: Optional[str] = None
    patient_count: int = 1
    
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    formatted_address: Optional[str] = None
    geocoding_confidence: float = 0.0

    severity: SeverityLevel
    recommended_ambulance_type: AmbulanceType
    ai_explanation: Optional[str] = None

    verification_status: Dict[str, Any] = {}
    rag_references: List[str] = []
    confidence_score: float = 0.0
    review_reason: Optional[str] = None

    is_duplicate: bool = False
    duplicate_of_incident_id: Optional[str] = None
    duplicate_similarity_score: float = 0.0

    status: IncidentStatus
    sla_deadline: Optional[datetime] = None
    is_sla_breached: bool = False
    assigned_ambulance_id: Optional[str] = None
    assigned_hospital_id: Optional[str] = None
    dispatcher_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DispatcherReviewAction(BaseModel):
    action: str = Field(..., description="'APPROVE' or 'OVERRIDE'")
    dispatcher_id: str
    override_severity: Optional[SeverityLevel] = None
    override_ambulance_type: Optional[AmbulanceType] = None
    override_hospital_id: Optional[str] = None
    override_ambulance_id: Optional[str] = None
    notes: Optional[str] = None

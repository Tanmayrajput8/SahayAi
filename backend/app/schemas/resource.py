from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.models.incident import AmbulanceType
from app.models.ambulance import AmbulanceStatus


class AmbulanceResponse(BaseModel):
    id: str
    vehicle_number: str
    ambulance_type: AmbulanceType
    base_station: str
    latitude: float
    longitude: float
    status: AmbulanceStatus
    equipment: List[str] = []
    contact_number: Optional[str] = None
    driver_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class HospitalResponse(BaseModel):
    id: str
    name: str
    address: str
    latitude: float
    longitude: float
    total_beds: int
    available_beds: int
    available_icu_beds: int
    has_trauma_center: bool
    has_cardiac_care: bool
    has_burn_unit: bool
    has_pediatric_icu: bool
    specializations: List[str] = []
    contact_phone: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ResourceMatchResult(BaseModel):
    matched_ambulance: Optional[AmbulanceResponse] = None
    ambulance_distance_km: float = 0.0
    ambulance_eta_minutes: float = 0.0
    matched_hospital: Optional[HospitalResponse] = None
    hospital_distance_km: float = 0.0
    explanation: str = ""
    match_score: float = 0.0
    is_dispatched: bool = True
    routing_provider: Optional[str] = None
    has_live_traffic: bool = False
    is_routing_fallback: bool = False
    traffic_disclaimer: str = "Static road network estimate; live traffic conditions are not included."

    model_config = ConfigDict(from_attributes=True)

# Re-export from case.py for complete backward compatibility
from app.models.case import (
    Case,
    Incident,
    SeverityLevel,
    AmbulanceType,
    CaseStatus,
    IncidentStatus,
)

__all__ = [
    "Case",
    "Incident",
    "SeverityLevel",
    "AmbulanceType",
    "CaseStatus",
    "IncidentStatus",
]

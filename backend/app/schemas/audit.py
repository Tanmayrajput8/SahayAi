from typing import Any, Dict
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.audit import AuditStage


class AuditLogResponse(BaseModel):
    id: str
    incident_id: str
    timestamp: datetime
    stage: AuditStage
    actor: str
    action: str
    details: Dict[str, Any] = {}
    latency_ms: int = 0

    model_config = ConfigDict(from_attributes=True)

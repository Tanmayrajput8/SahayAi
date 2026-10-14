from typing import Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: Optional[str] = None
    environment: Optional[str] = None
    database: Optional[str] = None

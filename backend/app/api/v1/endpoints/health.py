from fastapi import APIRouter
from app.core.config import settings
from app.db.session import check_db_connection
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse)
def get_health():
    """Versioned health check endpoint verifying database connectivity."""
    db_ok = check_db_connection()
    return HealthResponse(
        status="ok",
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        database="connected" if db_ok else "disconnected",
    )

"""System and Demo Administration Endpoints."""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.demo_reset import reset_demo_database

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/reset",
    summary="Reset Demo Data",
    description="Clears all demo emergency cases and restores simulated ambulances and hospitals to baseline.",
)
def reset_demo_endpoint(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Execute safe prototype demo reset."""
    return reset_demo_database(db=db)

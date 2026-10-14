"""Endpoints for Simulated Ambulance and Hospital Resource Verification."""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ambulance import Ambulance, AmbulanceStatus
from app.models.hospital import Hospital
from app.models.case import Case, AmbulanceType
from app.schemas.resource import (
    AmbulanceResponse,
    HospitalResponse,
    ResourceMatchResult,
)
from app.services.resource_verification import (
    verify_and_match_resources,
    ResourceVerificationError,
    InvalidLocationError,
    NoResourceAvailableError,
    AmbulanceUnavailableError,
    AmbulanceTypeMismatchError,
    HospitalUnavailableError,
)
from app.services.routing.factory import get_routing_provider
from app.services.routing.schemas import RouteResult

logger = logging.getLogger(__name__)

router = APIRouter()


class RouteQueryRequest(BaseModel):
    origin_lat: float = Field(..., ge=-90.0, le=90.0)
    origin_lon: float = Field(..., ge=-180.0, le=180.0)
    dest_lat: float = Field(..., ge=-90.0, le=90.0)
    dest_lon: float = Field(..., ge=-180.0, le=180.0)
    provider_name: Optional[str] = Field(default=None, description="Optional override: 'osrm', 'openrouteservice', 'fallback'")


@router.get(
    "/ambulances",
    response_model=List[AmbulanceResponse],
    summary="List Fleet Ambulances",
    description="Retrieve simulated fleet ambulances, optionally filtered by status or type.",
)
def list_ambulances(
    status_filter: Optional[AmbulanceStatus] = Query(default=None, alias="status"),
    type_filter: Optional[AmbulanceType] = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
) -> List[AmbulanceResponse]:
    query = db.query(Ambulance)
    if status_filter:
        query = query.filter(Ambulance.status == status_filter)
    if type_filter:
        query = query.filter(Ambulance.ambulance_type == type_filter)
    return [AmbulanceResponse.model_validate(a) for a in query.all()]


@router.get(
    "/hospitals",
    response_model=List[HospitalResponse],
    summary="List Emergency Hospitals",
    description="Retrieve simulated hospitals with current bed availability and specialty capabilities.",
)
def list_hospitals(
    active_only: bool = Query(default=True),
    has_cardiac: Optional[bool] = Query(default=None),
    has_trauma: Optional[bool] = Query(default=None),
    has_burns: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[HospitalResponse]:
    query = db.query(Hospital)
    if active_only:
        query = query.filter(Hospital.is_active == True)
    if has_cardiac is not None:
        query = query.filter(Hospital.has_cardiac_care == has_cardiac)
    if has_trauma is not None:
        query = query.filter(Hospital.has_trauma_center == has_trauma)
    if has_burns is not None:
        query = query.filter(Hospital.has_burn_unit == has_burns)
    return [HospitalResponse.model_validate(h) for h in query.all()]


@router.post(
    "/route",
    response_model=RouteResult,
    summary="Calculate Route ETA",
    description="Query external routing API (OSRM or OpenRouteService) with automatic lightweight fallback.",
)
def calculate_route_endpoint(payload: RouteQueryRequest) -> RouteResult:
    provider = get_routing_provider(payload.provider_name)
    return provider.calculate_route(
        origin_lat=payload.origin_lat,
        origin_lon=payload.origin_lon,
        dest_lat=payload.dest_lat,
        dest_lon=payload.dest_lon,
    )


@router.post(
    "/cases/{case_id}/match",
    response_model=ResourceMatchResult,
    summary="Verify & Dispatch Resources for Case",
    description=(
        "Executes 8-step resource verification algorithm: matches available BLS/ALS ambulances, "
        "filters top spatial candidates, queries external routing engine (OSRM/ORS) for ETA, "
        "verifies hospital bed and clinical capabilities, stores match, and updates ambulance status."
    ),
)
def match_case_resources_endpoint(
    case_id: str,
    strict_ambulance_type: bool = Query(default=False, description="Whether to reject if exact ALS/BLS type unavailable"),
    auto_dispatch: bool = Query(default=True, description="Update ambulance status to DISPATCHED immediately"),
    routing_provider_override: Optional[str] = Query(default=None, description="Force routing provider: 'osrm', 'openrouteservice', 'fallback'"),
    db: Session = Depends(get_db),
) -> ResourceMatchResult:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "not_found", "message": f"Emergency case '{case_id}' not found."},
        )

    provider = get_routing_provider(routing_provider_override) if routing_provider_override else None

    try:
        _, match_result = verify_and_match_resources(
            case_id=case_id,
            db=db,
            routing_provider=provider,
            strict_ambulance_type=strict_ambulance_type,
            auto_dispatch=auto_dispatch,
        )
        return match_result

    except InvalidLocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except AmbulanceTypeMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except AmbulanceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except (HospitalUnavailableError, NoResourceAvailableError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )
    except ResourceVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.code, "message": exc.message, "details": exc.details},
        )

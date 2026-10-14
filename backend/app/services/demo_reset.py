"""Service for safely resetting prototype emergency demo data."""
import logging
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.ambulance import Ambulance, AmbulanceStatus
from app.models.hospital import Hospital
from app.models.resource_match import ResourceMatch
from app.models.audit import AuditLog
from app.models.duplicate import DuplicateRelationship
from app.db.seed import SIMULATED_AMBULANCES, SIMULATED_HOSPITALS, seed_database

logger = logging.getLogger(__name__)


def reset_demo_database(db: Session) -> Dict[str, Any]:
    """
    Safely reset the emergency demo database:
    - Removes all created emergency cases and associated records
    - Restores ambulances to AVAILABLE status and baseline locations
    - Restores hospital bed capacities
    - Ensures seed users and protocols are intact
    """
    logger.info("Executing safe prototype demo reset...")

    # 1. Clear duplicate relationships first to avoid cyclic reference issues
    db.query(DuplicateRelationship).delete(synchronize_session=False)

    # 2. Clear all emergency cases (cascades to extracted_info, location, ai_decisions,
    #    resource_matches, verification_results, human_reviews, sla_tracking,
    #    escalation_events, audit_logs)
    cases_deleted = db.query(Case).count()
    db.query(Case).delete(synchronize_session=False)

    # 3. Clear any orphaned ResourceMatches or AuditLogs if any exist
    db.query(ResourceMatch).delete(synchronize_session=False)
    db.query(AuditLog).delete(synchronize_session=False)

    # 4. Restore ambulances to baseline available state and locations
    for a_data in SIMULATED_AMBULANCES:
        amb = db.query(Ambulance).filter(Ambulance.vehicle_number == a_data["vehicle_number"]).first()
        if amb:
            amb.status = AmbulanceStatus.AVAILABLE
            amb.latitude = a_data["latitude"]
            amb.longitude = a_data["longitude"]
        else:
            db.add(Ambulance(**a_data))

    # 5. Restore hospitals to baseline bed capacity
    for h_data in SIMULATED_HOSPITALS:
        hosp = db.query(Hospital).filter(Hospital.name == h_data["name"]).first()
        if hosp:
            hosp.available_beds = h_data["available_beds"]
            hosp.available_icu_beds = h_data["available_icu_beds"]
            hosp.is_active = True
        else:
            db.add(Hospital(**h_data))

    # 6. Ensure protocols and users are seeded
    seed_database(db)

    db.commit()
    logger.info("Demo reset complete: %d cases cleared.", cases_deleted)

    return {
        "status": "success",
        "message": "Demo data successfully reset. All cases cleared and fleet restored.",
        "cases_cleared": cases_deleted,
        "ambulances_available": len(SIMULATED_AMBULANCES),
        "hospitals_ready": len(SIMULATED_HOSPITALS),
    }

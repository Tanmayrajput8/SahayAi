from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, cases, resources, rag, review, sla, fairness, audit, system

api_router = APIRouter()

# Core system endpoints
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(system.router, prefix="/system", tags=["System Administration"])

# Authentication
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Emergency Intake & Cases
api_router.include_router(cases.router, prefix="/cases", tags=["Cases"])

# Simulated Resources & Routing Verification
api_router.include_router(resources.router, prefix="/resources", tags=["Resources & Dispatch"])

# RAG Knowledge Verification
api_router.include_router(rag.router, prefix="/rag", tags=["RAG Verification"])

# Human-in-the-Loop & Confidence
api_router.include_router(review.router, prefix="/review", tags=["Human Review & Confidence"])

# SLA Monitoring & Escalations
api_router.include_router(sla.router, prefix="/sla", tags=["SLA & Escalations"])

# Fairness & Demographic Evaluation
api_router.include_router(fairness.router, prefix="/fairness", tags=["Fairness Evaluation"])

# Comprehensive Audit Logging
api_router.include_router(audit.router, prefix="/audit", tags=["Audit Logging"])


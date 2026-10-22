from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging, logger
from app.db.session import Base, engine, SessionLocal
from app.db.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: setup logging, initialize DB tables
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} (env={settings.ENVIRONMENT}, version={settings.PROJECT_VERSION})")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    logger.info("Database initialized and simulated resources seeded successfully.")
    yield
    # Shutdown
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")


def create_application() -> FastAPI:
    """FastAPI Application Factory."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        description="SahayAI Emergency - AI Intelligence Layer for Ambulance Dispatch",
        docs_url="/docs",
        redoc_url="/redoc",
        swagger_ui_parameters={"persistAuthorization": True},
        lifespan=lifespan,
    )

    # 1. CORS Configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Global Exception Handlers (ensures consistent JSON error format)
    register_exception_handlers(app)

    # 3. Direct root health check as required: GET /health -> {"status": "ok"}
    @app.get("/health", tags=["Health"])
    def root_health():
        return {"status": "ok"}

    # 4. Versioned API Router: /api/v1/...
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # 5. Static Files & Multi-Role Page Routing
    import os
    from fastapi import Request, Response
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, RedirectResponse

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    citizen_index_html = os.path.join(static_dir, "index.html")
    citizen_track_html = os.path.join(static_dir, "citizen", "case-status.html")
    staff_login_html = os.path.join(static_dir, "staff", "login.html")
    staff_dashboard_html = os.path.join(static_dir, "staff", "dashboard.html")
    staff_cases_html = os.path.join(static_dir, "staff", "cases.html")
    staff_case_details_html = os.path.join(static_dir, "staff", "case-details.html")
    staff_review_html = os.path.join(static_dir, "staff", "review.html")
    staff_ambulances_html = os.path.join(static_dir, "staff", "ambulances.html")
    staff_hospitals_html = os.path.join(static_dir, "staff", "hospitals.html")
    staff_map_html = os.path.join(static_dir, "staff", "map.html")
    staff_sla_html = os.path.join(static_dir, "staff", "sla.html")
    staff_audit_html = os.path.join(static_dir, "staff", "audit.html")
    staff_fairness_html = os.path.join(static_dir, "staff", "fairness.html")

    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    # ── PUBLIC CITIZEN ROUTES ──────────────────────────────────
    @app.get("/", tags=["Citizen Portal", "Root"])
    def root(request: Request):
        format_param = request.query_params.get("format", "")
        accept = request.headers.get("accept", "")
        if format_param == "json" or ("application/json" in accept and "text/html" not in accept and "*/*" not in accept):
            return {
                "name": settings.PROJECT_NAME,
                "version": settings.PROJECT_VERSION,
                "docs": "/docs",
                "dashboard": "/staff/dashboard",
                "health": "/health",
                "api_v1": settings.API_V1_STR,
            }
        if os.path.exists(citizen_index_html):
            return FileResponse(citizen_index_html)
        return {"name": settings.PROJECT_NAME, "message": "Citizen Portal UI not found."}

    @app.get("/emergency", tags=["Citizen Portal"])
    def citizen_emergency_portal():
        if os.path.exists(citizen_index_html):
            return FileResponse(citizen_index_html)
        return {"name": settings.PROJECT_NAME, "message": "Emergency portal UI not found."}

    @app.get("/track", tags=["Citizen Portal"])
    @app.get("/track/{case_id}", tags=["Citizen Portal"])
    @app.get("/citizen/status", tags=["Citizen Portal"])
    def citizen_case_tracker(case_id: Optional[str] = None):

        if os.path.exists(citizen_track_html):
            return FileResponse(citizen_track_html)
        return {"name": settings.PROJECT_NAME, "message": "Citizen tracking UI not found."}

    # ── STAFF DISPATCHER & ADMIN ROUTES ────────────────────────
    @app.get("/staff/login", tags=["Staff Operations"])
    def staff_login_view():
        if os.path.exists(staff_login_html):
            return FileResponse(staff_login_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff login UI not found."}

    @app.get("/staff/dashboard", tags=["Staff Operations"])
    def staff_dashboard_view():
        if os.path.exists(staff_dashboard_html):
            return FileResponse(staff_dashboard_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff dashboard UI not found."}

    @app.get("/staff/cases", tags=["Staff Operations"])
    def staff_cases_view():
        if os.path.exists(staff_cases_html):
            return FileResponse(staff_cases_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff cases UI not found."}

    @app.get("/staff/cases/{case_id}", tags=["Staff Operations"])
    def staff_case_detail_view(case_id: str):
        if os.path.exists(staff_case_details_html):
            return FileResponse(staff_case_details_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff case detail UI not found."}

    @app.get("/staff/review", tags=["Staff Operations"])
    def staff_review_view():
        if os.path.exists(staff_review_html):
            return FileResponse(staff_review_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff review UI not found."}

    @app.get("/staff/ambulances", tags=["Staff Operations"])
    def staff_ambulances_view():
        if os.path.exists(staff_ambulances_html):
            return FileResponse(staff_ambulances_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff ambulances UI not found."}

    @app.get("/staff/hospitals", tags=["Staff Operations"])
    def staff_hospitals_view():
        if os.path.exists(staff_hospitals_html):
            return FileResponse(staff_hospitals_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff hospitals UI not found."}

    @app.get("/staff/map", tags=["Staff Operations"])
    def staff_map_view():
        if os.path.exists(staff_map_html):
            return FileResponse(staff_map_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff map UI not found."}

    @app.get("/staff/sla", tags=["Staff Operations"])
    def staff_sla_view():
        if os.path.exists(staff_sla_html):
            return FileResponse(staff_sla_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff SLA UI not found."}

    @app.get("/staff/audit", tags=["Staff Operations"])
    def staff_audit_view():
        if os.path.exists(staff_audit_html):
            return FileResponse(staff_audit_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff audit UI not found."}

    @app.get("/staff/fairness", tags=["Staff Operations"])
    def staff_fairness_view():
        if os.path.exists(staff_fairness_html):
            return FileResponse(staff_fairness_html)
        return {"name": settings.PROJECT_NAME, "message": "Staff fairness UI not found."}

    # ── CONVENIENCE REDIRECTS ──────────────────────────────────
    @app.get("/login", include_in_schema=False)
    def redirect_login():
        return RedirectResponse(url="/staff/login", status_code=302)

    @app.get("/dashboard", include_in_schema=False)
    def redirect_dashboard():
        return RedirectResponse(url="/staff/dashboard", status_code=302)

    # ── DEDICATED API ROOT METADATA ────────────────────────────
    @app.get("/api", tags=["Root"])
    def api_root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.PROJECT_VERSION,
            "docs": "/docs",
            "dashboard": "/staff/dashboard",
            "health": "/health",
            "api_v1": settings.API_V1_STR,
        }

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

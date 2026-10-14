from contextlib import asynccontextmanager
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

    # 5. Static Files & Dispatcher Dashboard UI
    import os
    from fastapi import Request, Response
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_html = os.path.join(static_dir, "index.html")

    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get("/login", tags=["Dashboard"])
    @app.get("/dashboard", tags=["Dashboard"])
    def serve_dashboard():
        if os.path.exists(index_html):
            return FileResponse(index_html)
        return {"name": settings.PROJECT_NAME, "message": "Dashboard UI not found."}

    # 6. Root web interface & API metadata
    @app.get("/", tags=["Dashboard", "Root"])
    def root(request: Request):
        format_param = request.query_params.get("format", "")
        accept = request.headers.get("accept", "")
        # If client explicitly requests json via format query param or specific Accept header without HTML:
        if format_param == "json" or ("application/json" in accept and "text/html" not in accept and "*/*" not in accept):
            return {
                "name": settings.PROJECT_NAME,
                "version": settings.PROJECT_VERSION,
                "docs": "/docs",
                "dashboard": "/dashboard",
                "health": "/health",
                "api_v1": settings.API_V1_STR,
            }
        # Default: open the main SahayAI Emergency web interface/dashboard
        if os.path.exists(index_html):
            return FileResponse(index_html)
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.PROJECT_VERSION,
            "docs": "/docs",
            "dashboard": "/dashboard",
            "health": "/health",
            "api_v1": settings.API_V1_STR,
        }

    # 7. Dedicated API metadata endpoint
    @app.get("/api", tags=["Root"])
    def api_root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.PROJECT_VERSION,
            "docs": "/docs",
            "dashboard": "/dashboard",
            "health": "/health",
            "api_v1": settings.API_V1_STR,
        }

    return app


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings
from app.core.logging import logger

# SQLite requires check_same_thread=False for multithreaded FastAPI requests
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass



def get_db():
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """Verify database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


def _ensure_sqlite_columns():
    """Ensure optional columns in existing SQLite tables are present without full rebuild."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            # ── cases table ──────────────────────────────────────────────────
            existing_cases = {row[1] for row in conn.execute(text("PRAGMA table_info(cases)")).fetchall()}
            if existing_cases:
                cases_col_defs = [
                    ("modality", "VARCHAR(32) NOT NULL DEFAULT 'text'"),
                    ("audio_url", "VARCHAR(512)"),
                    ("language", "VARCHAR(32) NOT NULL DEFAULT 'unknown'"),
                ]
                for col_name, col_type in cases_col_defs:
                    if col_name not in existing_cases:
                        conn.execute(text(f"ALTER TABLE cases ADD COLUMN {col_name} {col_type}"))
                        logger.info(f"DB migration: added cases.{col_name}")
                conn.commit()

            # ── ai_decisions table ────────────────────────────────────────────
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(ai_decisions)")).fetchall()}
            if existing:
                col_defs = [
                    ("ai_suggested_severity", "VARCHAR(32)"),
                    ("ai_suggested_ambulance", "VARCHAR(32)"),
                    ("deterministic_severity", "VARCHAR(32)"),
                    ("deterministic_ambulance", "VARCHAR(32)"),
                    ("has_conflict", "BOOLEAN DEFAULT 0"),
                    ("conflict_reason", "TEXT"),
                    ("decision_type", "VARCHAR(64) DEFAULT 'PROTOTYPE_DECISION_SUPPORT_HEURISTIC'"),
                    ("disclaimer", "TEXT DEFAULT 'PROTOTYPE DECISION-SUPPORT HEURISTIC - NOT CLINICALLY VALIDATED TRIAGE'"),
                    ("confidence_level", "VARCHAR(16) DEFAULT 'HIGH'"),
                    ("confidence_components", "JSON DEFAULT '{}'"),
                ]
                for col_name, col_type in col_defs:
                    if col_name not in existing:
                        conn.execute(text(f"ALTER TABLE ai_decisions ADD COLUMN {col_name} {col_type}"))
                conn.commit()

            loc_info = conn.execute(text("PRAGMA table_info(locations)")).fetchall()
            if loc_info:
                lat_col = next((r for r in loc_info if r[1] == "latitude"), None)
                if lat_col and lat_col[3] == 1:
                    # SQLite table was created with NOT NULL latitude, rebuild to allow nullable
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS _locations_migrated (
                            id VARCHAR(36) NOT NULL PRIMARY KEY,
                            case_id VARCHAR(36) NOT NULL,
                            raw_query VARCHAR(256) NOT NULL,
                            formatted_address TEXT,
                            latitude FLOAT,
                            longitude FLOAT,
                            city VARCHAR(64) DEFAULT 'Pune',
                            state VARCHAR(64) DEFAULT 'Maharashtra',
                            geocoding_provider VARCHAR(32) DEFAULT 'nominatim',
                            status VARCHAR(32) DEFAULT 'success',
                            confidence FLOAT DEFAULT 0.0,
                            is_verified BOOLEAN DEFAULT 0,
                            error_message TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(case_id) REFERENCES cases (id) ON DELETE CASCADE
                        )
                    """))
                    existing_cols = {r[1] for r in loc_info}
                    common_cols = [c for c in ["id", "case_id", "raw_query", "formatted_address", "latitude", "longitude", "city", "state", "geocoding_provider", "status", "confidence", "is_verified", "error_message", "created_at", "updated_at"] if c in existing_cols]
                    cols_str = ", ".join(common_cols)
                    conn.execute(text(f"INSERT INTO _locations_migrated ({cols_str}) SELECT {cols_str} FROM locations"))
                    conn.execute(text("DROP TABLE locations"))
                    conn.execute(text("ALTER TABLE _locations_migrated RENAME TO locations"))
                    conn.commit()

            existing_loc = {row[1] for row in conn.execute(text("PRAGMA table_info(locations)")).fetchall()}
            if existing_loc:
                loc_col_defs = [
                    ("status", "VARCHAR(32) DEFAULT 'success'"),
                    ("error_message", "TEXT"),
                ]
                for col_name, col_type in loc_col_defs:
                    if col_name not in existing_loc:
                        conn.execute(text(f"ALTER TABLE locations ADD COLUMN {col_name} {col_type}"))
                conn.commit()

            existing_sla = {row[1] for row in conn.execute(text("PRAGMA table_info(sla_tracking)")).fetchall()}
            if existing_sla:
                sla_col_defs = [
                    ("is_warning", "BOOLEAN DEFAULT 0"),
                    ("warning_triggered_at", "DATETIME"),
                    ("breached_at", "DATETIME"),
                    ("breach_duration_seconds", "INTEGER DEFAULT 0"),
                ]
                for col_name, col_type in sla_col_defs:
                    if col_name not in existing_sla:
                        conn.execute(text(f"ALTER TABLE sla_tracking ADD COLUMN {col_name} {col_type}"))
                conn.commit()
    except Exception as exc:
        logger.debug(f"SQLite column migration check skipped or failed: {exc}")


_ensure_sqlite_columns()

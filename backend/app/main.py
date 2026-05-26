"""
FastAPI application entry point.
Lifespan: starts APScheduler + runs initial sync on startup.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _ensure_test_campaign_columns(engine):
    """Add columns introduced after initial schema (SQLite-only)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "test_campaign" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("test_campaign")}
    with engine.begin() as conn:
        if "last_applied_action" not in existing:
            conn.execute(text("ALTER TABLE test_campaign ADD COLUMN last_applied_action VARCHAR"))
        if "last_applied_at" not in existing:
            conn.execute(text("ALTER TABLE test_campaign ADD COLUMN last_applied_at DATETIME"))


def _migrate_archer_product_day(engine):
    """
    Migrate archer_product_day to include geo as part of the primary key.
    Old PK: (asin, date).  New PK: (asin, date, geo).
    Existing rows are tagged geo='US'.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "archer_product_day" not in insp.get_table_names():
        return  # create_all will build the new schema
    existing_cols = {c["name"] for c in insp.get_columns("archer_product_day")}
    if "geo" in existing_cols:
        return  # already migrated
    logger.info("Migrating archer_product_day: adding geo column and rebuilding PK...")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE archer_product_day_new ("
            "  asin         TEXT NOT NULL,"
            "  date         DATE NOT NULL,"
            "  geo          TEXT NOT NULL DEFAULT 'US',"
            "  product_name TEXT,"
            "  revenue_usd  REAL DEFAULT 0.0,"
            "  orders       INTEGER DEFAULT 0,"
            "  units_sold   INTEGER DEFAULT 0,"
            "  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "  updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "  PRIMARY KEY (asin, date, geo)"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO archer_product_day_new "
            "(asin, date, geo, product_name, revenue_usd, orders, units_sold, created_at, updated_at) "
            "SELECT asin, date, 'US', product_name, revenue_usd, orders, units_sold, created_at, updated_at "
            "FROM archer_product_day"
        ))
        conn.execute(text("DROP TABLE archer_product_day"))
        conn.execute(text("ALTER TABLE archer_product_day_new RENAME TO archer_product_day"))
    logger.info("archer_product_day migration complete.")


def _purge_unused_data():
    """
    One-time startup cleanup: remove non-US archer rows and all product_catalog
    rows that were written during the multi-geo experiment.  Uses an in-memory
    journal so this works even when the volume is nearly full.
    """
    import os
    import sqlite3 as _sqlite3
    from .config import get_settings

    db_url = get_settings().database_url
    db_path = db_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return  # fresh DB, nothing to purge

    try:
        conn = _sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=MEMORY")
        cur = conn.execute("DELETE FROM product_catalog")
        pc_deleted = cur.rowcount
        cur = conn.execute("DELETE FROM archer_product_day WHERE geo != 'US'")
        non_us_deleted = cur.rowcount
        conn.commit()
        try:
            conn.execute("VACUUM")
        except Exception:
            pass  # VACUUM may fail if disk is still too full — safe to skip
        conn.close()
        if pc_deleted or non_us_deleted:
            logger.info(
                "Startup purge: deleted %d product_catalog rows, %d non-US archer rows.",
                pc_deleted, non_us_deleted,
            )
    except Exception:
        logger.exception("Startup purge failed (non-fatal)")


def _migrate_google_ads_country_code(engine):
    """Add country_code column to google_ads_campaign_day (nullable, defaults to NULL = US)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "google_ads_campaign_day" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("google_ads_campaign_day")}
    if "country_code" in existing_cols:
        return
    logger.info("Adding country_code column to google_ads_campaign_day...")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE google_ads_campaign_day ADD COLUMN country_code VARCHAR"))


def _migrate_google_ads_campaign_type(engine):
    """Add campaign_type column to google_ads_campaign_day (nullable, 'brand'|'amazon')."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "google_ads_campaign_day" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("google_ads_campaign_day")}
    if "campaign_type" not in existing_cols:
        logger.info("Adding campaign_type column to google_ads_campaign_day...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE google_ads_campaign_day ADD COLUMN campaign_type VARCHAR"))


def _migrate_campaign_job_campaign_type(engine):
    """Add campaign_type column to campaign_job (defaults to 'brand')."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "campaign_job" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("campaign_job")}
    if "campaign_type" not in existing_cols:
        logger.info("Adding campaign_type column to campaign_job...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE campaign_job ADD COLUMN campaign_type VARCHAR DEFAULT 'brand'"))


def _migrate_archer_total_sales_usd(engine):
    """Add total_sales_usd column to archer_product_day."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "archer_product_day" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("archer_product_day")}
    if "total_sales_usd" not in existing_cols:
        logger.info("Adding total_sales_usd column to archer_product_day...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE archer_product_day ADD COLUMN total_sales_usd REAL DEFAULT 0.0"))


def _migrate_attribution_link_cache_campaign_type(engine):
    """
    Rebuild attribution_link_cache with composite PK (asin, campaign_type).
    Old PK was (asin) alone. Existing rows are migrated as campaign_type='brand'.
    """
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "attribution_link_cache" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("attribution_link_cache")}
    if "campaign_type" in existing_cols:
        return
    logger.info("Migrating attribution_link_cache: adding campaign_type to PK...")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE attribution_link_cache_new ("
            "  asin          TEXT NOT NULL,"
            "  campaign_type TEXT NOT NULL DEFAULT 'brand',"
            "  url           TEXT NOT NULL,"
            "  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "  PRIMARY KEY (asin, campaign_type)"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO attribution_link_cache_new (asin, campaign_type, url, created_at) "
            "SELECT asin, 'brand', url, created_at FROM attribution_link_cache"
        ))
        conn.execute(text("DROP TABLE attribution_link_cache"))
        conn.execute(text("ALTER TABLE attribution_link_cache_new RENAME TO attribution_link_cache"))
    logger.info("attribution_link_cache migration complete.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("Starting up Ads Dashboard backend...")

    # Purge bloated data BEFORE opening SQLAlchemy (raw connection, memory journal)
    _purge_unused_data()

    # Create tables if they don't exist yet
    from .database import engine, Base
    from . import models  # noqa: F401

    # Run migrations before create_all so existing tables are updated first
    _migrate_archer_product_day(engine)
    _migrate_google_ads_country_code(engine)
    _migrate_google_ads_campaign_type(engine)
    _migrate_campaign_job_campaign_type(engine)
    _migrate_attribution_link_cache_campaign_type(engine)
    _ensure_test_campaign_columns(engine)
    _migrate_archer_total_sales_usd(engine)

    Base.metadata.create_all(bind=engine)

    # Start 4-hour scheduler (Archer only — Google Ads data comes via CSV upload)
    start_scheduler()

    # Run initial Archer sync in background so startup is non-blocking
    import threading
    def _startup_sync():
        from .services.sync_service import sync_archer, verify_warned_asins
        try:
            sync_archer()
        except Exception:
            logger.exception("Startup Archer sync failed (non-fatal)")
        try:
            verify_warned_asins()
        except Exception:
            logger.exception("Startup ASIN verification failed (non-fatal)")

    threading.Thread(target=_startup_sync, daemon=True, name="startup-sync").start()

    # Resume any campaign jobs that were in-progress when the server last stopped
    from .services.campaign_generator import resume_pending_jobs
    try:
        resume_pending_jobs()
    except Exception:
        logger.exception("Failed to resume campaign jobs (non-fatal)")

    yield  # app is running

    # ── Shutdown ───────────────────────────────────────────────────────────────
    stop_scheduler()
    logger.info("Ads Dashboard backend shut down.")


app = FastAPI(
    title="Ads Performance Dashboard",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS — allow local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from .api.routes_health import router as health_router
from .api.routes_sync import router as sync_router
from .api.routes_dashboard import router as dashboard_router
from .api.routes_upload import router as upload_router
from .api.routes_testing import router as testing_router
from .api.routes_catalog import router as catalog_router
from .api.routes_campaigns import router as campaigns_router
from .api.routes_campaign_create import router as campaign_create_router

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(sync_router, tags=["sync"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(upload_router, tags=["upload"])
app.include_router(testing_router, tags=["testing"])
app.include_router(catalog_router, tags=["catalog"])
app.include_router(campaigns_router, tags=["campaigns"])
app.include_router(campaign_create_router, tags=["campaign_creator"])

# Serve built React frontend (production only — not present in local dev)
import os
from pathlib import Path
_frontend_dist = Path(__file__).parent.parent / "frontend_dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    from .config import get_settings
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.backend_port, reload=True)

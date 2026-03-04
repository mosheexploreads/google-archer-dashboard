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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("Starting up Ads Dashboard backend...")

    # Create tables if they don't exist yet
    from .database import engine, Base
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Start 4-hour scheduler (Archer only — Google Ads data comes via CSV upload)
    start_scheduler()

    # Run initial Archer sync in background so startup is non-blocking
    import threading
    def _startup_sync():
        from .services.sync_service import sync_archer
        try:
            sync_archer()
        except Exception:
            logger.exception("Startup Archer sync failed (non-fatal)")

    threading.Thread(target=_startup_sync, daemon=True, name="startup-sync").start()

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

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(sync_router, tags=["sync"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(upload_router, tags=["upload"])

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

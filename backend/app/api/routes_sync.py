from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SyncLog
from ..schemas import SyncStatus, SyncSourceStatus, TriggerResponse
from ..scheduler import trigger_sync_now, get_next_run
from ..services.sync_service import is_running

router = APIRouter(prefix="/api/sync")


def _latest_sync(db: Session, source: str) -> SyncSourceStatus:
    log = (
        db.query(SyncLog)
        .filter_by(source=source)
        .order_by(SyncLog.id.desc())
        .first()
    )
    return SyncSourceStatus(
        source=source,
        last_sync=log.finished_at if log else None,
        last_status=log.status if log else None,
        rows_last_sync=log.records_upserted if log else None,
    )


@router.get("/status", response_model=SyncStatus)
def sync_status(db: Session = Depends(get_db)):
    return SyncStatus(
        google_ads=_latest_sync(db, "google_ads"),
        archer=_latest_sync(db, "archer"),
        next_run=get_next_run(),
        is_syncing=is_running(),
    )


@router.post("/trigger", response_model=TriggerResponse)
def trigger_sync():
    trigger_sync_now()
    return TriggerResponse(message="Sync triggered. Check /api/sync/status for progress.")


@router.post("/check-products", response_model=TriggerResponse)
def trigger_product_check():
    """Manually trigger ASIN removal verification against Archer API."""
    import threading
    from ..services.sync_service import verify_warned_asins
    threading.Thread(target=verify_warned_asins, daemon=True, name="manual-asin-check").start()
    return TriggerResponse(message="ASIN removal check started in background.")


@router.get("/maintenance/purge-db")
def purge_unused_data():
    """
    One-time maintenance: delete unused data using an in-memory journal
    so the operation works even when the disk is full.
    """
    import logging
    import os
    import sqlite3
    from ..config import get_settings

    logger = logging.getLogger(__name__)
    settings = get_settings()

    # Resolve the actual file path from the DATABASE_URL
    db_url = settings.database_url  # e.g. sqlite:////data/ads_dashboard.db
    db_path = db_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return {"status": "error", "message": f"DB not found at {db_path}"}

    size_before = round(os.path.getsize(db_path) / 1024 / 1024, 1)
    results: dict = {"db_path": db_path, "db_size_mb_before": size_before}

    conn = sqlite3.connect(db_path)
    try:
        # Use in-memory journal — no disk space needed for the journal file
        conn.execute("PRAGMA journal_mode=MEMORY")

        cur = conn.execute("DELETE FROM product_catalog")
        results["product_catalog_deleted"] = cur.rowcount

        cur = conn.execute("DELETE FROM archer_product_day WHERE geo != 'US'")
        results["archer_non_us_deleted"] = cur.rowcount

        conn.commit()

        # VACUUM reclaims freed pages; needs temp space equal to DB size.
        # Use VACUUM INTO a temp file then swap, or just try and catch.
        try:
            conn.execute("VACUUM")
            conn.commit()
        except Exception as e:
            results["vacuum_error"] = str(e)

    finally:
        conn.close()

    try:
        results["db_size_mb_after"] = round(os.path.getsize(db_path) / 1024 / 1024, 1)
    except Exception:
        pass

    logger.info("DB maintenance complete: %s", results)
    return {"status": "ok", "results": results}

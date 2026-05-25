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
def purge_unused_data(db: Session = Depends(get_db)):
    """
    One-time maintenance: delete unused data (product_catalog + non-US archer rows)
    then VACUUM to reclaim disk space.
    """
    import logging
    import os
    from ..database import engine
    logger = logging.getLogger(__name__)

    results = {}

    # Delete all product_catalog rows (feature is hidden, 223k+ rows from debug sync)
    r = db.execute(text("DELETE FROM product_catalog"))
    results["product_catalog_deleted"] = r.rowcount

    # Delete non-US archer_product_day rows (EU/FE/CA — not used, inflate DB)
    r = db.execute(text("DELETE FROM archer_product_day WHERE geo != 'US'"))
    results["archer_non_us_deleted"] = r.rowcount

    db.commit()

    # VACUUM must run outside a transaction — use a raw connection
    with engine.connect() as conn:
        conn.execute(text("VACUUM"))

    # Report DB file size after vacuum
    db_path = str(engine.url).replace("sqlite:///", "")
    try:
        results["db_size_mb_after"] = round(os.path.getsize(db_path) / 1024 / 1024, 1)
    except Exception:
        pass

    logger.info("DB maintenance complete: %s", results)
    return {"status": "ok", "deleted": results}

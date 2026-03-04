from fastapi import APIRouter, Depends
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

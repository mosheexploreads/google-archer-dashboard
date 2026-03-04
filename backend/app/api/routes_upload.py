"""
POST /api/upload/google-ads  — accepts a Google Ads CSV report file.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import GoogleAdsCampaignDay, SyncLog
from ..services.csv_parser import parse_google_ads_csv

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/upload")


class UploadResult(BaseModel):
    rows_imported: int
    date_from: str
    date_to: str
    campaigns: int
    message: str


_MODEL_FIELDS = {"campaign_id", "date", "campaign_name", "asin", "impressions", "clicks", "spend_usd", "campaign_status"}


def _upsert_rows(db: Session, rows: list[dict]) -> int:
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    count = 0
    for row in rows:
        clean = {k: v for k, v in row.items() if k in _MODEL_FIELDS}
        clean["updated_at"] = datetime.utcnow()
        stmt = sqlite_insert(GoogleAdsCampaignDay).values(**clean)
        stmt = stmt.on_conflict_do_update(
            index_elements=["campaign_id", "date"],
            set_={k: v for k, v in clean.items() if k not in ("campaign_id", "date")},
        )
        db.execute(stmt)
        count += 1
    db.commit()
    return count


@router.post("/google-ads", response_model=UploadResult)
async def upload_google_ads_csv(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50 MB guard
        raise HTTPException(status_code=400, detail="File too large (max 50 MB)")

    try:
        records = parse_google_ads_csv(content)
    except (ValueError, Exception) as e:
        logger.exception("CSV parse failed")
        status = 422 if isinstance(e, ValueError) else 500
        raise HTTPException(status_code=status, detail=f"Parse error: {e}")

    db = SessionLocal()
    count = 0
    date_from = date_to = None
    try:
        dates = [r["date"] for r in records]
        date_from = min(dates)
        date_to = max(dates)

        log = SyncLog(
            source="csv_upload",
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()

        count = _upsert_rows(db, records)
        log.status = "success"
        log.finished_at = datetime.utcnow()
        log.records_upserted = count
        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("CSV upload failed")
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    finally:
        db.close()

    campaigns = len({r["campaign_name"] for r in records})
    return UploadResult(
        rows_imported=count,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        campaigns=campaigns,
        message=f"Successfully imported {count} rows across {campaigns} campaigns ({date_from} – {date_to}).",
    )

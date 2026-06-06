"""
POST /api/upload/google-ads  — accepts a Google Ads CSV report file.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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


_MODEL_FIELDS = {"campaign_id", "date", "campaign_name", "account", "asin", "country_code", "campaign_type", "impressions", "clicks", "spend_usd", "campaign_status"}


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


@router.delete("/google-ads/date/{report_date}")
def delete_google_ads_date(report_date: str):
    """Delete all google_ads_campaign_day rows for a specific date (YYYY-MM-DD). Use before re-uploading."""
    from sqlalchemy import text
    try:
        from datetime import datetime as _dt
        _dt.strptime(report_date, "%Y-%m-%d")  # validate format
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    db = SessionLocal()
    try:
        result = db.execute(text("DELETE FROM google_ads_campaign_day WHERE date = :d"), {"d": report_date})
        db.commit()
        deleted = result.rowcount
        logger.info("Deleted %d Google Ads rows for %s", deleted, report_date)
        return {"date": report_date, "rows_deleted": deleted, "message": f"Deleted {deleted} rows for {report_date}. Safe to re-upload."}
    finally:
        db.close()


@router.post("/google-ads", response_model=UploadResult)
async def upload_google_ads_csv(
    file: UploadFile = File(...),
    account: str = Form(""),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    account = account.strip()
    if not account:
        raise HTTPException(status_code=422, detail="Account name is required — pick which Google Ads account this report is for.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50 MB guard
        raise HTTPException(status_code=400, detail="File too large (max 50 MB)")

    try:
        records = parse_google_ads_csv(content, account)
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

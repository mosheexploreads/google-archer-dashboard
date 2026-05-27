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


def _max_google_ads_date(db: Session) -> str | None:
    """Return the latest date present in google_ads_campaign_day, or None."""
    row = db.execute(text("SELECT MAX(date) AS d FROM google_ads_campaign_day")).fetchone()
    return str(row.d) if row and row.d else None


@router.get("/status", response_model=SyncStatus)
def sync_status(db: Session = Depends(get_db)):
    return SyncStatus(
        # google_ads field tracks CSV uploads, not API (API path is disabled).
        google_ads=_latest_sync(db, "csv_upload"),
        archer=_latest_sync(db, "archer"),
        next_run=get_next_run(),
        is_syncing=is_running(),
        google_ads_data_through=_max_google_ads_date(db),
    )


@router.post("/trigger", response_model=TriggerResponse)
def trigger_sync():
    trigger_sync_now()
    return TriggerResponse(message="Sync triggered. Check /api/sync/status for progress.")


@router.get("/debug/config")
def debug_config():
    """Return the active configuration values (non-secret) to verify Railway env vars."""
    from ..config import get_settings
    settings = get_settings()
    return {
        "archer_base_url": settings.archer_base_url,
        "archer_username": settings.archer_username,
        "archer_markets": settings.archer_markets,
        "database_url": settings.database_url,
    }


@router.get("/debug/archer")
def debug_archer(
    date_from: str = "2026-05-25",
    date_to: str = "2026-05-25",
    db: Session = Depends(get_db),
):
    """
    Call Archer /product_reports_all directly and return what we get.
    Also shows what's stored in the DB for the same date range.
    Use to diagnose sync vs UI discrepancies.
    """
    from datetime import datetime
    from ..services.archer_client import ArcherClient
    from ..services.sync_service import _parse_archer_date

    d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    d_to   = datetime.strptime(date_to,   "%Y-%m-%d").date()

    # 1. Call Archer API directly
    try:
        client = ArcherClient()
        raw = client.fetch_earnings(d_from, d_to, geo=None)
    except Exception as exc:
        return {"error": str(exc)}

    # Aggregate the same way sync_archer does
    aggregated: dict = {}
    skipped = 0
    for row in raw:
        parsed_date = _parse_archer_date(row.get("date"))
        if not row.get("asin") or parsed_date is None:
            skipped += 1
            continue
        key = (row["asin"].upper(), str(parsed_date))
        if key not in aggregated:
            aggregated[key] = {"asin": row["asin"].upper(), "date": str(parsed_date),
                               "revenue_usd": 0.0, "orders": 0, "units_sold": 0}
        aggregated[key]["revenue_usd"] += row["revenue_usd"]
        aggregated[key]["orders"]      += row["orders"]
        aggregated[key]["units_sold"]  += row["units_sold"]

    api_rows = sorted(aggregated.values(), key=lambda r: -r["revenue_usd"])
    api_total = sum(r["revenue_usd"] for r in api_rows)

    # 2. What's currently in the DB for the same range
    db_rows = db.execute(text(
        "SELECT asin, SUM(revenue_usd) AS rev, SUM(orders) AS ord "
        "FROM archer_product_day "
        "WHERE date BETWEEN :df AND :dt AND geo = 'US' "
        "GROUP BY asin ORDER BY rev DESC"
    ), {"df": date_from, "dt": date_to}).fetchall()

    db_total = sum(r.rev for r in db_rows)

    return {
        "date_range": f"{date_from} → {date_to}",
        "archer_api": {
            "total_raw_rows":  len(raw),
            "skipped_rows":    skipped,
            "unique_asins":    len(aggregated),
            "total_revenue":   round(api_total, 2),
            "rows":            api_rows[:20],  # top 20
        },
        "db": {
            "unique_asins":  len(db_rows),
            "total_revenue": round(db_total, 2),
            "rows":          [{"asin": r.asin, "revenue_usd": round(r.rev, 2), "orders": r.ord}
                              for r in db_rows[:20]],
        },
        "gap": round(api_total - db_total, 2),
    }


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

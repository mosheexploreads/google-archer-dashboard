"""
Sync service: orchestrates fetching data from Google Ads and Archer,
then upserts into SQLite.
"""
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..database import SessionLocal
from ..models import GoogleAdsCampaignDay, ArcherProductDay, SyncLog
from ..utils.asin_extractor import extract_asin
from ..utils.date_utils import yesterday, days_ago
from .google_ads_client import GoogleAdsClient
from .archer_client import ArcherClient

logger = logging.getLogger(__name__)

_is_running = False


def is_running() -> bool:
    return _is_running


def _log_sync(
    db: Session,
    source: str,
    status: str,
    started_at: datetime,
    records: int = 0,
    error: Optional[str] = None,
):
    entry = SyncLog(
        source=source,
        status=status,
        started_at=started_at,
        finished_at=datetime.utcnow(),
        records_upserted=records,
        error_message=error,
    )
    db.add(entry)
    db.commit()


def _already_synced_google(db: Session, report_date: date) -> bool:
    """Returns True if we have a successful Google Ads sync for this date."""
    from sqlalchemy import select, func
    count = db.execute(
        select(func.count()).select_from(GoogleAdsCampaignDay)
        .where(GoogleAdsCampaignDay.date == report_date)
    ).scalar()
    return (count or 0) > 0


def sync_google_ads() -> int:
    """Fetch yesterday's Google Ads data and upsert. Skips if already synced."""
    report_date = yesterday()
    started = datetime.utcnow()
    db = SessionLocal()
    try:
        if _already_synced_google(db, report_date):
            logger.info("Google Ads: already synced for %s, skipping.", report_date)
            _log_sync(db, "google_ads", "skipped", started)
            return 0

        client = GoogleAdsClient()
        rows = client.fetch_campaign_stats(report_date)

        count = 0
        for row in rows:
            asin = extract_asin(row["campaign_name"])
            stmt = sqlite_insert(GoogleAdsCampaignDay).values(
                campaign_id=row["campaign_id"],
                date=report_date,
                campaign_name=row["campaign_name"],
                asin=asin,
                impressions=row["impressions"],
                clicks=row["clicks"],
                spend_usd=row["spend_usd"],
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["campaign_id", "date"],
                set_={
                    "campaign_name": stmt.excluded.campaign_name,
                    "asin":          stmt.excluded.asin,
                    "impressions":   stmt.excluded.impressions,
                    "clicks":        stmt.excluded.clicks,
                    "spend_usd":     stmt.excluded.spend_usd,
                    "updated_at":    datetime.utcnow(),
                },
            )
            db.execute(stmt)
            count += 1

        db.commit()
        _log_sync(db, "google_ads", "success", started, records=count)
        logger.info("Google Ads: upserted %d rows for %s.", count, report_date)
        return count

    except Exception as exc:
        db.rollback()
        _log_sync(db, "google_ads", "error", started, error=str(exc))
        logger.error("Google Ads sync failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


def _parse_archer_date(raw) -> Optional[date]:
    """Convert whatever Archer returns for date into a Python date object."""
    if isinstance(raw, date):
        return raw
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def sync_archer() -> int:
    """Fetch D-30 through D-1 from Archer and upsert. Safe to re-run."""
    date_from = days_ago(30)
    date_to   = days_ago(1)
    started   = datetime.utcnow()
    db        = SessionLocal()
    try:
        client = ArcherClient()
        rows   = client.fetch_earnings(date_from, date_to)

        # Aggregate by (asin, date) before upserting — the API returns one row
        # per link/campaign, so the same ASIN can appear multiple times on the
        # same date. Without aggregation the upsert would silently overwrite and
        # lose revenue from all but the last row.
        aggregated: dict[tuple, dict] = {}
        skipped = 0
        for row in rows:
            parsed_date = _parse_archer_date(row.get("date"))
            if not row.get("asin") or parsed_date is None:
                skipped += 1
                continue
            key = (row["asin"].upper(), parsed_date)
            if key not in aggregated:
                aggregated[key] = {
                    "asin":         row["asin"].upper(),
                    "date":         parsed_date,
                    "product_name": row.get("product_name"),
                    "revenue_usd":  row["revenue_usd"],
                    "orders":       row["orders"],
                    "units_sold":   row["units_sold"],
                }
            else:
                aggregated[key]["revenue_usd"] += row["revenue_usd"]
                aggregated[key]["orders"]      += row["orders"]
                aggregated[key]["units_sold"]  += row["units_sold"]

        count = 0
        for agg in aggregated.values():
            stmt = sqlite_insert(ArcherProductDay).values(**agg)
            stmt = stmt.on_conflict_do_update(
                index_elements=["asin", "date"],
                set_={
                    "product_name": stmt.excluded.product_name,
                    "revenue_usd":  stmt.excluded.revenue_usd,
                    "orders":       stmt.excluded.orders,
                    "units_sold":   stmt.excluded.units_sold,
                    "updated_at":   datetime.utcnow(),
                },
            )
            db.execute(stmt)
            count += 1

        db.commit()
        _log_sync(db, "archer", "success", started, records=count)
        logger.info("Archer: upserted %d rows, skipped %d for %s–%s.", count, skipped, date_from, date_to)
        return count

    except Exception as exc:
        db.rollback()
        _log_sync(db, "archer", "error", started, error=str(exc))
        logger.error("Archer sync failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


def run_full_sync():
    """Run both syncs. Called by scheduler and manual trigger."""
    global _is_running
    if _is_running:
        logger.warning("Sync already in progress, skipping.")
        return
    _is_running = True
    try:
        sync_google_ads()
    except Exception:
        pass  # logged inside; don't abort Archer sync
    try:
        sync_archer()
    except Exception:
        pass
    finally:
        _is_running = False

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
from ..models import GoogleAdsCampaignDay, ArcherProductDay, ProductCatalog, SyncLog, ArcherAsinStatus
from ..utils.asin_extractor import extract_asin
from ..utils.geo_utils import ARCHER_GEOS, country_to_geo
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
    """Fetch D-30 through D-1 from Archer for all geos and upsert. Safe to re-run."""
    date_from = days_ago(30)
    date_to   = days_ago(1)
    started   = datetime.utcnow()
    db        = SessionLocal()
    total_count = 0
    try:
        client = ArcherClient()

        for geo in ARCHER_GEOS:
            rows = client.fetch_earnings(date_from, date_to, geo=None if geo == "US" else geo)

            # Aggregate by (asin, date, geo) — API may return one row per link.
            aggregated: dict[tuple, dict] = {}
            skipped = 0
            for row in rows:
                parsed_date = _parse_archer_date(row.get("date"))
                if not row.get("asin") or parsed_date is None:
                    skipped += 1
                    continue
                key = (row["asin"].upper(), parsed_date, geo)
                if key not in aggregated:
                    aggregated[key] = {
                        "asin":         row["asin"].upper(),
                        "date":         parsed_date,
                        "geo":          geo,
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
                    index_elements=["asin", "date", "geo"],
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
            logger.info("Archer [%s]: upserted %d rows, skipped %d for %s–%s.", geo, count, skipped, date_from, date_to)
            total_count += count

        _log_sync(db, "archer", "success", started, records=total_count)
        return total_count

    except Exception as exc:
        db.rollback()
        _log_sync(db, "archer", "error", started, error=str(exc))
        logger.error("Archer sync failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


def sync_product_catalog() -> int:
    """Fetch product catalog from Archer for all configured markets and upsert."""
    from ..config import get_settings
    settings = get_settings()
    markets = [m.strip().upper() for m in settings.archer_markets.split(",") if m.strip()]
    started = datetime.utcnow()
    db = SessionLocal()
    total_count = 0
    try:
        client = ArcherClient()
        for country_code in markets:
            products = client.fetch_products(country_code)
            count = 0
            for p in products:
                stmt = sqlite_insert(ProductCatalog).values(
                    asin=p["asin"],
                    country_code=country_code,
                    product_name=p.get("product_name"),
                    price=p.get("price"),
                    rating=p.get("rating"),
                    review_count=p.get("review_count"),
                    image_url=p.get("image_url"),
                    availability=p.get("availability"),
                    affiliate_url=p.get("affiliate_url"),
                    last_synced_at=datetime.utcnow(),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["asin", "country_code"],
                    set_={
                        "product_name":  stmt.excluded.product_name,
                        "price":         stmt.excluded.price,
                        "rating":        stmt.excluded.rating,
                        "review_count":  stmt.excluded.review_count,
                        "image_url":     stmt.excluded.image_url,
                        "availability":  stmt.excluded.availability,
                        "affiliate_url": stmt.excluded.affiliate_url,
                        "last_synced_at": stmt.excluded.last_synced_at,
                    },
                )
                db.execute(stmt)
                count += 1
            db.commit()
            logger.info("Archer catalog [%s]: upserted %d products.", country_code, count)
            total_count += count

        _log_sync(db, "archer_catalog", "success", started, records=total_count)
        return total_count

    except Exception as exc:
        db.rollback()
        _log_sync(db, "archer_catalog", "error", started, error=str(exc))
        logger.error("Archer catalog sync failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


def verify_warned_asins() -> int:
    """
    For every enabled campaign whose ASIN is missing from recent Archer data,
    call /get_single_product to confirm whether the product is truly removed.
    Updates archer_asin_status table. Returns count of removed ASINs found.
    """
    from sqlalchemy import text
    started = datetime.utcnow()
    db = SessionLocal()
    removed_count = 0
    try:
        # Get all unique ASINs from enabled campaigns that have ever had Archer data
        # but are now absent 2+ days (same candidates as the warning banner)
        sql = text("""
            WITH archer_last AS (
                SELECT asin, MAX(date) AS last_date
                FROM archer_product_day
                GROUP BY asin
            ),
            max_archer AS (
                SELECT MAX(date) AS max_date FROM archer_product_day
            )
            SELECT DISTINCT g.asin
            FROM google_ads_campaign_day g
            INNER JOIN (
                SELECT campaign_id, MAX(date) AS max_date
                FROM google_ads_campaign_day
                WHERE campaign_status IS NOT NULL
                GROUP BY campaign_id
            ) ld ON g.campaign_id = ld.campaign_id AND g.date = ld.max_date
            JOIN archer_last al ON g.asin = al.asin
            CROSS JOIN max_archer ma
            WHERE g.campaign_status = 'Enabled'
              AND g.asin IS NOT NULL
              AND CAST(julianday(ma.max_date) - julianday(al.last_date) AS INTEGER) >= 2
        """)
        rows = db.execute(sql).fetchall()
        asins = [r[0] for r in rows]
        logger.info("verify_warned_asins: checking %d ASINs against Archer API", len(asins))

        if not asins:
            return 0

        client = ArcherClient()
        now = datetime.utcnow()

        for asin in asins:
            try:
                result = client.check_asin(asin)
            except Exception as exc:
                logger.warning("check_asin(%s) failed: %s", asin, exc)
                continue

            existing = db.get(ArcherAsinStatus, asin)
            if existing:
                existing.is_active = 1 if result["is_active"] else 0
                existing.last_checked_at = now
                if not result["is_active"] and existing.removed_at is None:
                    existing.removed_at = now
                if result["is_active"]:
                    existing.removed_at = None
                if result["product_name"]:
                    existing.product_name = result["product_name"]
            else:
                db.add(ArcherAsinStatus(
                    asin=asin,
                    is_active=1 if result["is_active"] else 0,
                    product_name=result["product_name"],
                    last_checked_at=now,
                    removed_at=None if result["is_active"] else now,
                ))

            if not result["is_active"]:
                removed_count += 1

        db.commit()
        logger.info("verify_warned_asins: %d removed, %d active out of %d checked",
                    removed_count, len(asins) - removed_count, len(asins))
        return removed_count

    except Exception as exc:
        db.rollback()
        logger.error("verify_warned_asins failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


def run_full_sync():
    """Run all syncs. Called by scheduler and manual trigger."""
    global _is_running
    if _is_running:
        logger.warning("Sync already in progress, skipping.")
        return
    _is_running = True
    try:
        sync_google_ads()
    except Exception:
        pass
    try:
        sync_archer()
    except Exception:
        pass
    try:
        sync_product_catalog()
    except Exception:
        pass
    finally:
        _is_running = False

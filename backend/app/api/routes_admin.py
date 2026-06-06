"""
Admin-only endpoints for maintenance tasks.
"""
import logging
from fastapi import APIRouter, HTTPException
from datetime import datetime
from sqlalchemy import text

from ..database import SessionLocal
from ..models import ProductCatalog
from ..services.archer_client import ArcherClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")


@router.get("/db-stats")
def db_stats():
    """Disk usage + row counts so we can see what's filling the Railway volume."""
    import os
    from ..config import get_settings
    settings = get_settings()
    db_path = settings.database_url.replace("sqlite:///", "")
    out: dict = {"db_path": db_path}

    # Actual files on disk (main DB + WAL + SHM)
    for suffix, label in [("", "db_file_mb"), ("-wal", "wal_file_mb"), ("-shm", "shm_file_mb")]:
        p = db_path + suffix
        out[label] = round(os.path.getsize(p) / 1024 / 1024, 1) if os.path.exists(p) else 0

    db = SessionLocal()
    try:
        # Logical DB size from SQLite page accounting
        pc = db.execute(text("PRAGMA page_count")).scalar() or 0
        ps = db.execute(text("PRAGMA page_size")).scalar() or 0
        out["sqlite_logical_mb"] = round(pc * ps / 1024 / 1024, 1)
        out["freelist_mb"] = round((db.execute(text("PRAGMA freelist_count")).scalar() or 0) * ps / 1024 / 1024, 1)

        # Row counts for the big tables
        tables = ["google_ads_campaign_day", "product_catalog", "archer_product_day",
                  "discovery_candidate", "discovery_result"]
        counts = {}
        for t in tables:
            try:
                counts[t] = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            except Exception:
                counts[t] = None
        out["row_counts"] = counts

        # How many google_ads rows are zero-activity (the prunable bulk)
        out["google_ads_zero_activity_rows"] = db.execute(text(
            "SELECT COUNT(*) FROM google_ads_campaign_day"
            " WHERE COALESCE(impressions,0)=0 AND COALESCE(clicks,0)=0 AND COALESCE(spend_usd,0)=0"
        )).scalar()
        return out
    finally:
        db.close()


@router.get("/account-stats")
def account_stats():
    """Row + distinct-campaign counts per account label (NULL shown as 'unlabeled')."""
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT COALESCE(account, '(unlabeled)') AS account,"
            "       COUNT(*) AS rows,"
            "       COUNT(DISTINCT campaign_id) AS campaigns,"
            "       MIN(date) AS first_date, MAX(date) AS last_date"
            " FROM google_ads_campaign_day"
            " GROUP BY COALESCE(account, '(unlabeled)')"
            " ORDER BY rows DESC"
        )).fetchall()
        return {"accounts": [dict(r._mapping) for r in rows]}
    finally:
        db.close()


@router.post("/reassign-account")
def reassign_account(from_account: str, to_account: str, date_from: str = "", date_to: str = ""):
    """
    Reassign every row currently labeled `from_account` to `to_account`.
    Optionally scope to a date range (inclusive). Use to correct a mislabeled
    upload, e.g. ?from_account=Explorads&to_account=Archer.
    """
    db = SessionLocal()
    try:
        sql = "UPDATE google_ads_campaign_day SET account = :to WHERE account = :frm"
        params = {"to": to_account, "frm": from_account}
        if date_from and date_to:
            sql += " AND date BETWEEN :df AND :dt"
            params["df"] = date_from
            params["dt"] = date_to
        res = db.execute(text(sql), params)
        db.commit()  # after_commit hook clears the dashboard cache
        logger.info("Reassigned %d rows from account %r to %r", res.rowcount, from_account, to_account)
        return {
            "status": "success",
            "from_account": from_account,
            "to_account": to_account,
            "date_from": date_from or None,
            "date_to": date_to or None,
            "rows_updated": res.rowcount,
        }
    finally:
        db.close()


@router.post("/sync/catalog")
def sync_product_catalog(country_code: str = "US"):
    """
    Fetch the full Archer product catalog and populate product_catalog table.
    This is a long-running operation (can take several minutes for 200K products).

    Call manually when you want to refresh the catalog:
    POST /api/admin/sync/catalog?country_code=US
    """
    db = SessionLocal()
    try:
        logger.info("Starting product catalog sync for %s...", country_code)

        # Clear existing data for this country
        deleted = db.query(ProductCatalog).filter(
            ProductCatalog.country_code == country_code
        ).delete()
        db.commit()
        logger.info("Cleared %d existing products for %s", deleted, country_code)

        # Fetch from Archer
        archer = ArcherClient()
        all_products = archer.fetch_products(country_code)
        logger.info("Fetched %d products from Archer", len(all_products))

        # Insert into DB in batches, skipping duplicates
        inserted = 0
        skipped_dups = 0
        for product in all_products:
            # Check if ASIN already exists (skip duplicates/variants)
            existing = db.query(ProductCatalog).filter(
                ProductCatalog.asin == product["asin"],
                ProductCatalog.country_code == country_code
            ).first()
            if existing:
                skipped_dups += 1
                continue

            catalog_row = ProductCatalog(
                asin=product["asin"],
                country_code=country_code,
                product_name=product["product_name"],
                price=product["price"],
                rating=product["rating"],
                review_count=product["review_count"],
                image_url=product["image_url"],
                availability=product["availability"],
                affiliate_url=product["affiliate_url"],
                last_synced_at=datetime.utcnow(),
            )
            db.add(catalog_row)
            inserted += 1

            if inserted % 10000 == 0:
                db.commit()
                logger.info("  Inserted %d rows, skipped %d duplicates...", inserted, skipped_dups)

        db.commit()
        logger.info("Catalog sync complete: %d products inserted, %d duplicates skipped for %s",
                   inserted, skipped_dups, country_code)

        # Return stats
        total = db.query(ProductCatalog).filter(
            ProductCatalog.country_code == country_code
        ).count()
        with_rating = db.query(ProductCatalog).filter(
            ProductCatalog.country_code == country_code,
            ProductCatalog.rating.isnot(None)
        ).count()
        matching = db.query(ProductCatalog).filter(
            ProductCatalog.country_code == country_code,
            ProductCatalog.rating >= 4.2,
            ProductCatalog.review_count >= 100
        ).count()

        return {
            "status": "success",
            "country_code": country_code,
            "total_products": total,
            "with_rating": with_rating,
            "matching_filter_4_2_100": matching,
        }

    except Exception as e:
        logger.exception("Catalog sync failed")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
    finally:
        db.close()

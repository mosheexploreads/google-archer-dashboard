"""
Admin-only endpoints for maintenance tasks.
"""
import logging
from fastapi import APIRouter, HTTPException
from datetime import datetime

from ..database import SessionLocal
from ..models import ProductCatalog
from ..services.archer_client import ArcherClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")


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

        # Insert into DB in batches
        inserted = 0
        for product in all_products:
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
                logger.info("  Inserted %d rows...", inserted)

        db.commit()
        logger.info("Catalog sync complete: %d products inserted for %s", inserted, country_code)

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

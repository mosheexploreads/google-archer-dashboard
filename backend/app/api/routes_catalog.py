"""
Product catalog endpoints.

GET  /api/catalog/products          — paginated catalog with optional country + search filter
POST /api/catalog/sync              — trigger background catalog sync
GET  /api/catalog/sync/status       — last sync time per market
"""
import logging
import threading
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import ProductCatalog, SyncLog
from ..schemas import ProductCatalogItem, ProductCatalogResponse, CatalogSyncStatus, CatalogSyncStatusResponse, TriggerResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/catalog")


@router.get("/products", response_model=ProductCatalogResponse)
def list_catalog_products(
    country_code: str = Query("", description="Filter by country code (UK, DE, JP, CA)"),
    search: str = Query("", description="Partial match on product name or ASIN"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(ProductCatalog)
    if country_code:
        q = q.filter(ProductCatalog.country_code == country_code.upper())
    if search:
        like = f"%{search}%"
        q = q.filter(
            (ProductCatalog.asin.ilike(like)) | (ProductCatalog.product_name.ilike(like))
        )

    total = q.count()
    rows = q.order_by(ProductCatalog.country_code, ProductCatalog.asin).offset((page - 1) * limit).limit(limit).all()

    return ProductCatalogResponse(
        items=[
            ProductCatalogItem(
                asin=r.asin,
                country_code=r.country_code,
                product_name=r.product_name,
                price=r.price,
                rating=r.rating,
                review_count=r.review_count,
                image_url=r.image_url,
                availability=r.availability,
                affiliate_url=r.affiliate_url,
                last_synced_at=r.last_synced_at,
            )
            for r in rows
        ],
        total=total,
    )


@router.post("/sync", response_model=TriggerResponse)
def trigger_catalog_sync():
    """Trigger an immediate product catalog sync in the background."""
    def _run():
        from ..services.sync_service import sync_product_catalog
        try:
            sync_product_catalog()
        except Exception:
            logger.exception("Catalog sync failed (background)")

    threading.Thread(target=_run, daemon=True, name="catalog-sync").start()
    return TriggerResponse(message="Catalog sync started in background.")


@router.get("/debug")
def catalog_debug(db: Session = Depends(get_db)):
    """Debug: show settings and test fetch_products for UK."""
    from ..config import get_settings
    from ..services.archer_client import ArcherClient
    settings = get_settings()
    markets = [m.strip().upper() for m in settings.archer_markets.split(",") if m.strip()]
    result = {
        "archer_base_url": settings.archer_base_url,
        "archer_markets_raw": settings.archer_markets,
        "markets_parsed": markets,
    }
    try:
        client = ArcherClient()
        products = client.fetch_products("UK")
        result["uk_products_fetched"] = len(products)
        result["uk_sample"] = products[0] if products else None
    except Exception as e:
        result["fetch_error"] = str(e)
    return result


@router.get("/sync/log")
def catalog_sync_log(db: Session = Depends(get_db)):
    """Return last 10 SyncLog entries for archer_catalog — debug helper."""
    rows = (
        db.query(SyncLog)
        .filter(SyncLog.source == "archer_catalog")
        .order_by(SyncLog.started_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "started_at": str(r.started_at),
            "finished_at": str(r.finished_at),
            "status": r.status,
            "records_upserted": r.records_upserted,
            "error_message": r.error_message,
        }
        for r in rows
    ]


@router.get("/sync/status", response_model=CatalogSyncStatusResponse)
def catalog_sync_status(db: Session = Depends(get_db)):
    """Return last sync time and product count per market."""
    rows = (
        db.query(
            ProductCatalog.country_code,
            func.max(ProductCatalog.last_synced_at).label("last_synced_at"),
            func.count(ProductCatalog.asin).label("records"),
        )
        .group_by(ProductCatalog.country_code)
        .all()
    )
    return CatalogSyncStatusResponse(
        markets=[
            CatalogSyncStatus(
                country_code=r.country_code,
                last_synced_at=r.last_synced_at,
                records=r.records,
            )
            for r in rows
        ]
    )

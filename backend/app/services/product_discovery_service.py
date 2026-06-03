"""
Product discovery service.

Pipeline:
  1. Fetch all US products from Archer catalog
  2. Filter: rating >= min_rating AND review_count >= min_reviews
  3. For each qualifying ASIN: check Amazon subcategory rank via Rainforest API
  4. Keep products with rank <= max_rank in ANY subcategory
  5. Flag ASINs that already have an active Google Ads campaign

Runs in a background thread; updates DiscoveryScan progress in DB as it goes.
"""
import logging
import time
from datetime import datetime
from typing import Set

from ..database import SessionLocal
from ..models import DiscoveryScan, DiscoveryResult
from .archer_client import ArcherClient
from .rainforest_client import RainforestClient

logger = logging.getLogger(__name__)

_is_running = False


def is_running() -> bool:
    return _is_running


def _get_existing_campaign_asins(db) -> Set[str]:
    """Return the set of ASINs that already have at least one Google Ads campaign."""
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT DISTINCT asin FROM google_ads_campaign_day WHERE asin IS NOT NULL"
    )).fetchall()
    return {r[0].upper() for r in rows}


def run_discovery_scan(scan_id: int, min_rating: float, min_reviews: int, max_rank: int):
    """
    Background worker — runs the full discovery pipeline for scan_id.
    Designed to be called from a daemon thread.
    """
    global _is_running
    _is_running = True
    db = SessionLocal()

    try:
        scan = db.get(DiscoveryScan, scan_id)
        if not scan:
            logger.error("DiscoveryScan %d not found", scan_id)
            return

        # ── Step 1: Fetch Archer US catalog ─────────────────────────────────
        logger.info("Discovery scan %d: fetching Archer catalog...", scan_id)
        try:
            archer = ArcherClient()
            products = archer.fetch_products("US")
        except Exception as exc:
            logger.error("Discovery scan %d: Archer fetch failed: %s", scan_id, exc)
            scan.status = "error"
            scan.error = f"Archer fetch failed: {exc}"
            scan.finished_at = datetime.utcnow()
            db.commit()
            return

        scan.total_archer = len(products)
        db.commit()
        logger.info("Discovery scan %d: fetched %d Archer products", scan_id, len(products))

        # ── Step 2: Filter by rating / review_count ──────────────────────────
        qualified = [
            p for p in products
            if (p.get("rating") or 0) >= min_rating
            and (p.get("review_count") or 0) >= min_reviews
        ]
        scan.total_filtered = len(qualified)
        db.commit()
        logger.info(
            "Discovery scan %d: %d products passed rating/review filter",
            scan_id, len(qualified),
        )

        # ── Step 3: Existing campaign ASINs ──────────────────────────────────
        existing_asins = _get_existing_campaign_asins(db)

        # ── Step 4: Check Rainforest BSR per qualifying ASIN ─────────────────
        rainforest = RainforestClient()
        found = 0

        for i, product in enumerate(qualified):
            asin = (product.get("asin") or "").upper()
            if not asin:
                continue

            # Small delay to be polite to the API (2 req/s)
            if i > 0:
                time.sleep(0.5)

            best = rainforest.get_top_subcategory_rank(asin, max_rank)
            scan.total_ranked = i + 1
            db.commit()

            if best is None:
                continue

            result = DiscoveryResult(
                scan_id=scan_id,
                asin=asin,
                product_name=product.get("product_name"),
                rating=product.get("rating"),
                review_count=product.get("review_count"),
                price=product.get("price"),
                image_url=product.get("image_url"),
                affiliate_url=product.get("affiliate_url"),
                subcategory=best.get("category"),
                rank=best.get("rank"),
                has_campaign=1 if asin in existing_asins else 0,
                created_at=datetime.utcnow(),
            )
            db.add(result)
            found += 1

            if found % 10 == 0:
                db.commit()
                logger.info("Discovery scan %d: found %d qualifying products so far", scan_id, found)

        # ── Finalise ─────────────────────────────────────────────────────────
        scan.total_found = found
        scan.status = "complete"
        scan.finished_at = datetime.utcnow()
        db.commit()
        logger.info(
            "Discovery scan %d complete: %d top-%d products out of %d qualified / %d total",
            scan_id, found, max_rank, len(qualified), len(products),
        )

    except Exception as exc:
        logger.exception("Discovery scan %d failed unexpectedly", scan_id)
        try:
            scan = db.get(DiscoveryScan, scan_id)
            if scan:
                scan.status = "error"
                scan.error = str(exc)
                scan.finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _is_running = False

"""
Product discovery service — two independent phases.

Phase 1 — run_archer_scan(scan_id)
  Fetches the full Archer US catalog, filters by min_rating / min_reviews,
  saves qualifying ASINs to discovery_candidate. Fast (~30 sec).

Phase 2 — run_rank_scan(scan_id)
  Reads discovery_candidate rows for scan_id, calls Rainforest API for each,
  keeps products with subcategory rank <= max_rank, saves to discovery_result.
  Slow (0.5 s/ASIN — can take several minutes for large catalogs).

Each phase runs in its own daemon thread and updates DiscoveryScan progress.
"""
import logging
import time
from datetime import datetime
from typing import Set

from ..database import SessionLocal
from ..models import DiscoveryScan, DiscoveryCandidate, DiscoveryResult
from .archer_client import ArcherClient
from .rainforest_client import RainforestClient

logger = logging.getLogger(__name__)

_archer_running = False
_rank_running = False


def is_archer_running() -> bool:
    return _archer_running


def is_rank_running() -> bool:
    return _rank_running


def _get_existing_campaign_asins(db) -> Set[str]:
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT DISTINCT asin FROM google_ads_campaign_day WHERE asin IS NOT NULL"
    )).fetchall()
    return {r[0].upper() for r in rows}


# ── Phase 1 ───────────────────────────────────────────────────────────────────

def run_archer_scan(scan_id: int):
    """
    Phase 1: fetch Archer catalog → filter → save to discovery_candidate.
    Runs in a daemon thread.
    """
    global _archer_running
    _archer_running = True
    db = SessionLocal()
    try:
        scan = db.get(DiscoveryScan, scan_id)
        if not scan:
            logger.error("DiscoveryScan %d not found", scan_id)
            return

        scan.archer_status = "running"
        scan.archer_started_at = datetime.utcnow()
        db.commit()

        # Fetch full catalog from Archer (US)
        logger.info("Discovery scan %d Phase 1: fetching Archer catalog...", scan_id)
        try:
            archer = ArcherClient()
            products = archer.fetch_products("US")
        except Exception as exc:
            logger.error("Discovery scan %d Phase 1: Archer fetch failed: %s", scan_id, exc)
            scan.archer_status = "error"
            scan.archer_error = f"Archer fetch failed: {exc}"
            scan.archer_finished_at = datetime.utcnow()
            db.commit()
            return

        scan.total_archer = len(products)
        db.commit()
        logger.info("Discovery scan %d: fetched %d Archer products", scan_id, len(products))

        # Filter by rating / review_count
        min_rating = scan.min_rating or 4.2
        min_reviews = scan.min_reviews or 100

        existing_asins = _get_existing_campaign_asins(db)

        qualified = [
            p for p in products
            if (p.get("rating") or 0) >= min_rating
            and (p.get("review_count") or 0) >= min_reviews
        ]

        # Save candidates
        for p in qualified:
            asin = (p.get("asin") or "").upper()
            if not asin:
                continue
            db.add(DiscoveryCandidate(
                scan_id=scan_id,
                asin=asin,
                product_name=p.get("product_name"),
                rating=p.get("rating"),
                review_count=p.get("review_count"),
                price=p.get("price"),
                image_url=p.get("image_url"),
                affiliate_url=p.get("affiliate_url"),
                has_campaign=1 if asin in existing_asins else 0,
            ))

        scan.total_filtered = len(qualified)
        scan.archer_status = "complete"
        scan.archer_finished_at = datetime.utcnow()
        db.commit()
        logger.info(
            "Discovery scan %d Phase 1 complete: %d / %d passed filter",
            scan_id, len(qualified), len(products),
        )

    except Exception as exc:
        logger.exception("Discovery scan %d Phase 1 failed", scan_id)
        try:
            scan = db.get(DiscoveryScan, scan_id)
            if scan:
                scan.archer_status = "error"
                scan.archer_error = str(exc)
                scan.archer_finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _archer_running = False


# ── Phase 2 ───────────────────────────────────────────────────────────────────

def run_rank_scan(scan_id: int):
    """
    Phase 2: check Amazon BSR via Rainforest for each candidate → save qualifying
    products to discovery_result. Runs in a daemon thread.
    """
    global _rank_running
    _rank_running = True
    db = SessionLocal()
    try:
        scan = db.get(DiscoveryScan, scan_id)
        if not scan:
            logger.error("DiscoveryScan %d not found", scan_id)
            return

        scan.rank_status = "running"
        scan.rank_started_at = datetime.utcnow()
        scan.total_ranked = 0
        scan.total_found = 0
        db.commit()

        # Load candidates
        candidates = (
            db.query(DiscoveryCandidate)
            .filter(DiscoveryCandidate.scan_id == scan_id)
            .all()
        )
        if not candidates:
            scan.rank_status = "error"
            scan.rank_error = "No candidates found — run Archer scan first."
            scan.rank_finished_at = datetime.utcnow()
            db.commit()
            return

        max_rank = scan.max_rank or 5
        rainforest = RainforestClient()
        found = 0

        logger.info(
            "Discovery scan %d Phase 2: checking %d ASINs via Rainforest (max_rank=%d)...",
            scan_id, len(candidates), max_rank,
        )

        for i, candidate in enumerate(candidates):
            if i > 0:
                time.sleep(0.5)  # ~2 req/s — polite rate limit

            best = rainforest.get_top_subcategory_rank(candidate.asin, max_rank)

            scan.total_ranked = i + 1
            if (i + 1) % 20 == 0:
                db.commit()
                logger.info(
                    "Discovery scan %d Phase 2: %d/%d checked, %d qualified",
                    scan_id, i + 1, len(candidates), found,
                )

            if best is None:
                continue

            db.add(DiscoveryResult(
                scan_id=scan_id,
                asin=candidate.asin,
                product_name=candidate.product_name,
                rating=candidate.rating,
                review_count=candidate.review_count,
                price=candidate.price,
                image_url=candidate.image_url,
                affiliate_url=candidate.affiliate_url,
                subcategory=best.get("category"),
                rank=best.get("rank"),
                has_campaign=candidate.has_campaign,
                created_at=datetime.utcnow(),
            ))
            found += 1

        scan.total_found = found
        scan.rank_status = "complete"
        scan.rank_finished_at = datetime.utcnow()
        db.commit()
        logger.info(
            "Discovery scan %d Phase 2 complete: %d top-%d products out of %d candidates",
            scan_id, found, max_rank, len(candidates),
        )

    except Exception as exc:
        logger.exception("Discovery scan %d Phase 2 failed", scan_id)
        try:
            scan = db.get(DiscoveryScan, scan_id)
            if scan:
                scan.rank_status = "error"
                scan.rank_error = str(exc)
                scan.rank_finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _rank_running = False

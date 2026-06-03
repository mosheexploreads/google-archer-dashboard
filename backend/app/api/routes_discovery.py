"""
Product discovery endpoints.

POST /api/discovery/scan          — start a new scan (background)
GET  /api/discovery/scan/latest   — latest scan status + progress
GET  /api/discovery/results       — qualified products from latest complete scan
"""
import logging
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from ..database import SessionLocal
from ..models import DiscoveryScan, DiscoveryResult
from ..services.product_discovery_service import run_discovery_scan, is_running

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery")


# ── Request / Response schemas ────────────────────────────────────────────────

class ScanRequest(BaseModel):
    min_rating: float = 4.2
    min_reviews: int = 100
    max_rank: int = 5


class ScanStatus(BaseModel):
    id: int
    status: str
    min_rating: float
    min_reviews: int
    max_rank: int
    total_archer: int
    total_filtered: int
    total_ranked: int
    total_found: int
    started_at: str
    finished_at: Optional[str]
    error: Optional[str]
    progress_pct: float   # 0–100


class DiscoveryProductRow(BaseModel):
    id: int
    asin: str
    product_name: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]
    price: Optional[float]
    image_url: Optional[str]
    affiliate_url: Optional[str]
    subcategory: Optional[str]
    rank: Optional[int]
    has_campaign: bool


class DiscoveryResultsResponse(BaseModel):
    scan_id: int
    total: int
    new_only: int   # without existing campaigns
    products: List[DiscoveryProductRow]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scan", response_model=ScanStatus)
def start_scan(req: ScanRequest):
    """Start a new discovery scan in the background. Returns immediately."""
    if is_running():
        raise HTTPException(status_code=409, detail="A scan is already running.")

    db = SessionLocal()
    try:
        scan = DiscoveryScan(
            status="running",
            min_rating=req.min_rating,
            min_reviews=req.min_reviews,
            max_rank=req.max_rank,
            started_at=datetime.utcnow(),
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)
        scan_id = scan.id

        # Fire background thread
        t = threading.Thread(
            target=run_discovery_scan,
            args=(scan_id, req.min_rating, req.min_reviews, req.max_rank),
            daemon=True,
            name=f"discovery-scan-{scan_id}",
        )
        t.start()

        return _scan_to_status(scan)
    finally:
        db.close()


@router.get("/scan/latest", response_model=Optional[ScanStatus])
def get_latest_scan():
    """Return the most recent scan's status and progress."""
    db = SessionLocal()
    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT * FROM discovery_scan ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if not row:
            return None
        scan = db.get(DiscoveryScan, row.id)
        return _scan_to_status(scan)
    finally:
        db.close()


@router.get("/results", response_model=DiscoveryResultsResponse)
def get_results(hide_existing: bool = Query(False)):
    """
    Return qualified products from the latest complete scan.
    Pass hide_existing=true to exclude ASINs that already have campaigns.
    """
    db = SessionLocal()
    try:
        from sqlalchemy import text
        scan_row = db.execute(text(
            "SELECT id FROM discovery_scan WHERE status = 'complete' ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if not scan_row:
            raise HTTPException(status_code=404, detail="No completed scan found. Run a scan first.")

        scan_id = scan_row.id
        from sqlalchemy.orm import Session
        results: List[DiscoveryResult] = (
            db.query(DiscoveryResult)
            .filter(DiscoveryResult.scan_id == scan_id)
            .order_by(DiscoveryResult.rank.asc())
            .all()
        )

        products = [_result_to_row(r) for r in results]
        new_only = sum(1 for p in products if not p.has_campaign)

        if hide_existing:
            products = [p for p in products if not p.has_campaign]

        return DiscoveryResultsResponse(
            scan_id=scan_id,
            total=len(results),
            new_only=new_only,
            products=products,
        )
    finally:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scan_to_status(scan: DiscoveryScan) -> ScanStatus:
    total_to_check = scan.total_filtered or 0
    ranked = scan.total_ranked or 0
    pct = (ranked / total_to_check * 100) if total_to_check > 0 else (
        100.0 if scan.status == "complete" else 0.0
    )
    return ScanStatus(
        id=scan.id,
        status=scan.status,
        min_rating=scan.min_rating,
        min_reviews=scan.min_reviews,
        max_rank=scan.max_rank,
        total_archer=scan.total_archer or 0,
        total_filtered=scan.total_filtered or 0,
        total_ranked=scan.total_ranked or 0,
        total_found=scan.total_found or 0,
        started_at=str(scan.started_at),
        finished_at=str(scan.finished_at) if scan.finished_at else None,
        error=scan.error,
        progress_pct=round(min(pct, 100.0), 1),
    )


def _result_to_row(r: DiscoveryResult) -> DiscoveryProductRow:
    return DiscoveryProductRow(
        id=r.id,
        asin=r.asin,
        product_name=r.product_name,
        rating=r.rating,
        review_count=r.review_count,
        price=r.price,
        image_url=r.image_url,
        affiliate_url=r.affiliate_url,
        subcategory=r.subcategory,
        rank=r.rank,
        has_campaign=bool(r.has_campaign),
    )

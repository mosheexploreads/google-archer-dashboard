"""
Product discovery endpoints — two independent phases.

Phase 1 (Archer):
  POST /api/discovery/scan/archer    — start Archer catalog scan
  GET  /api/discovery/candidates     — filtered products from Phase 1

Phase 2 (Rainforest ranking):
  POST /api/discovery/scan/rank      — start ranking check on Phase 1 results
  GET  /api/discovery/results        — top-N qualified products from Phase 2

Shared:
  GET  /api/discovery/scan/latest    — full status of both phases
"""
import logging
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from ..database import SessionLocal
from ..models import DiscoveryScan, DiscoveryCandidate, DiscoveryResult
from ..services.product_discovery_service import (
    run_archer_scan, run_rank_scan,
    is_archer_running, is_rank_running,
    request_stop, is_stop_requested,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/discovery")


# ── Schemas ───────────────────────────────────────────────────────────────────

class ArcherScanRequest(BaseModel):
    min_rating: float = 4.2
    min_reviews: int = 100
    result_limit: int = 1000  # stop after N qualifying products found


class RankScanRequest(BaseModel):
    max_rank: int = 5


class ScanStatus(BaseModel):
    id: int
    # Phase 1
    archer_status: str
    min_rating: float
    min_reviews: int
    result_limit: int
    total_archer: int
    total_filtered: int
    archer_started_at: Optional[str]
    archer_finished_at: Optional[str]
    archer_error: Optional[str]
    # Phase 2
    rank_status: str
    max_rank: int
    total_ranked: int
    total_found: int
    rank_started_at: Optional[str]
    rank_finished_at: Optional[str]
    rank_error: Optional[str]
    # Derived
    rank_progress_pct: float


class ProductRow(BaseModel):
    id: int
    asin: str
    product_name: Optional[str]
    rating: Optional[float]
    review_count: Optional[int]
    price: Optional[float]
    image_url: Optional[str]
    affiliate_url: Optional[str]
    has_campaign: bool


class RankedProductRow(ProductRow):
    subcategory: Optional[str]
    rank: Optional[int]


class CandidatesResponse(BaseModel):
    scan_id: int
    total: int
    new_only: int
    products: List[ProductRow]


class ResultsResponse(BaseModel):
    scan_id: int
    total: int
    new_only: int
    products: List[RankedProductRow]


# ── Phase 1 endpoints ─────────────────────────────────────────────────────────

@router.post("/scan/archer", response_model=ScanStatus)
def start_archer_scan(req: ArcherScanRequest):
    """Start Phase 1: fetch & filter Archer catalog. Creates a new scan session."""
    if is_archer_running():
        raise HTTPException(status_code=409, detail="An Archer scan is already running.")

    db = SessionLocal()
    try:
        scan = DiscoveryScan(
            archer_status="running",
            min_rating=req.min_rating,
            min_reviews=req.min_reviews,
            result_limit=req.result_limit,
            rank_status="idle",
            max_rank=5,
            archer_started_at=datetime.utcnow(),
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)
        scan_id = scan.id

        threading.Thread(
            target=run_archer_scan,
            args=(scan_id,),
            daemon=True,
            name=f"archer-scan-{scan_id}",
        ).start()

        return _to_status(scan)
    finally:
        db.close()


@router.get("/candidates", response_model=CandidatesResponse)
def get_candidates(hide_existing: bool = Query(False)):
    """Phase 1 results: products that passed the Archer rating/review filter."""
    db = SessionLocal()
    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT id FROM discovery_scan "
            "WHERE archer_status = 'complete' ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No completed Archer scan. Run Phase 1 first.")

        scan_id = row.id
        candidates: List[DiscoveryCandidate] = (
            db.query(DiscoveryCandidate)
            .filter(DiscoveryCandidate.scan_id == scan_id)
            .order_by(DiscoveryCandidate.review_count.desc())
            .all()
        )

        products = [_candidate_to_row(c) for c in candidates]
        new_only = sum(1 for p in products if not p.has_campaign)

        if hide_existing:
            products = [p for p in products if not p.has_campaign]

        return CandidatesResponse(scan_id=scan_id, total=len(candidates), new_only=new_only, products=products)
    finally:
        db.close()


# ── Phase 2 endpoints ─────────────────────────────────────────────────────────

@router.post("/scan/rank", response_model=ScanStatus)
def start_rank_scan(req: RankScanRequest):
    """Start Phase 2: check Amazon BSR via Rainforest for Phase 1 candidates."""
    if is_rank_running():
        raise HTTPException(status_code=409, detail="A ranking scan is already running.")

    db = SessionLocal()
    try:
        from sqlalchemy import text

        # Find the latest scan with candidates ready
        row = db.execute(text(
            "SELECT id FROM discovery_scan "
            "WHERE archer_status = 'complete' ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Run Phase 1 (Archer scan) first.")

        scan = db.get(DiscoveryScan, row.id)

        # Clear previous Phase 2 results for this scan
        db.query(DiscoveryResult).filter(DiscoveryResult.scan_id == scan.id).delete()
        scan.rank_status = "running"
        scan.rank_started_at = datetime.utcnow()
        scan.max_rank = req.max_rank
        scan.total_ranked = 0
        scan.total_found = 0
        scan.rank_error = None
        db.commit()

        scan_id = scan.id
        threading.Thread(
            target=run_rank_scan,
            args=(scan_id,),
            daemon=True,
            name=f"rank-scan-{scan_id}",
        ).start()

        db.refresh(scan)
        return _to_status(scan)
    finally:
        db.close()


@router.get("/results", response_model=ResultsResponse)
def get_results(hide_existing: bool = Query(False)):
    """Phase 2 results: products ranked top N in their Amazon subcategory."""
    db = SessionLocal()
    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT id FROM discovery_scan "
            "WHERE rank_status = 'complete' ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No completed ranking scan. Run Phase 2 first.")

        scan_id = row.id
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

        return ResultsResponse(scan_id=scan_id, total=len(results), new_only=new_only, products=products)
    finally:
        db.close()


# ── Shared ────────────────────────────────────────────────────────────────────

@router.post("/scan/stop")
def stop_scan():
    """Signal the currently running scan to stop at the next page boundary.

    Checks the database state, not global flags, so it works even if a scan
    thread crashed or the app was restarted mid-scan.
    """
    db = SessionLocal()
    try:
        # Find the most recent scan
        scan = db.query(DiscoveryScan).order_by(DiscoveryScan.id.desc()).first()

        # Check if either phase is running according to the database
        if not scan or (scan.archer_status not in ("running", "idle") and
                       scan.rank_status not in ("running", "idle")):
            raise HTTPException(status_code=409, detail="No scan is currently running.")

        # If database says it's running, signal the stop
        if scan.archer_status == "running" or scan.rank_status == "running":
            request_stop()
            return {"message": "Stop signal sent. Scan will halt at the next checkpoint."}
        else:
            raise HTTPException(status_code=409, detail="No scan is currently running.")
    finally:
        db.close()


@router.get("/scan/latest", response_model=Optional[ScanStatus])
def get_latest_scan():
    """Return status of both phases for the most recent scan session."""
    db = SessionLocal()
    try:
        from sqlalchemy import text
        row = db.execute(text(
            "SELECT * FROM discovery_scan ORDER BY id DESC LIMIT 1"
        )).fetchone()
        if not row:
            return None
        scan = db.get(DiscoveryScan, row.id)
        return _to_status(scan)
    finally:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_status(scan: DiscoveryScan) -> ScanStatus:
    total = scan.total_filtered or 0
    ranked = scan.total_ranked or 0
    pct = (ranked / total * 100) if total > 0 else (
        100.0 if scan.rank_status == "complete" else 0.0
    )
    return ScanStatus(
        id=scan.id,
        archer_status=scan.archer_status,
        min_rating=scan.min_rating or 4.2,
        min_reviews=scan.min_reviews or 100,
        result_limit=scan.result_limit or 1000,
        total_archer=scan.total_archer or 0,
        total_filtered=scan.total_filtered or 0,
        archer_started_at=str(scan.archer_started_at) if scan.archer_started_at else None,
        archer_finished_at=str(scan.archer_finished_at) if scan.archer_finished_at else None,
        archer_error=scan.archer_error,
        rank_status=scan.rank_status,
        max_rank=scan.max_rank or 5,
        total_ranked=scan.total_ranked or 0,
        total_found=scan.total_found or 0,
        rank_started_at=str(scan.rank_started_at) if scan.rank_started_at else None,
        rank_finished_at=str(scan.rank_finished_at) if scan.rank_finished_at else None,
        rank_error=scan.rank_error,
        rank_progress_pct=round(min(pct, 100.0), 1),
    )


def _candidate_to_row(c: DiscoveryCandidate) -> ProductRow:
    return ProductRow(
        id=c.id,
        asin=c.asin,
        product_name=c.product_name,
        rating=c.rating,
        review_count=c.review_count,
        price=c.price,
        image_url=c.image_url,
        affiliate_url=c.affiliate_url,
        has_campaign=bool(c.has_campaign),
    )


def _result_to_row(r: DiscoveryResult) -> RankedProductRow:
    return RankedProductRow(
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

"""
Testing module endpoints.

POST /api/testing/batch   — upload batch CSV of campaigns to test
GET  /api/testing/status  — current action status for all test campaigns
GET  /api/testing/export  — download Google Ads Editor bulk CSV
"""
import io
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..database import SessionLocal
from ..models import TestBatch, TestCampaign
from ..schemas import TestBatchUploadResult, TestStatusResponse
from ..services.testing_engine import (
    parse_batch_csv,
    evaluate_campaigns,
    build_google_ads_export,
    _cut_threshold,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/testing")


@router.post("/batch", response_model=TestBatchUploadResult)
async def upload_test_batch(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    try:
        records = parse_batch_csv(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Batch CSV parse failed")
        raise HTTPException(status_code=500, detail=f"Parse error: {e}")

    db = SessionLocal()
    try:
        batch_name = (file.filename or "batch").removesuffix(".csv")
        batch = TestBatch(name=batch_name, campaign_count=len(records))
        db.add(batch)
        db.flush()  # populate batch.id before inserting children

        for r in records:
            aov = r["price"] * r["commission_rate"]
            db.add(
                TestCampaign(
                    batch_id=batch.id,
                    campaign_name=r["campaign_name"],
                    asin=r["asin"],
                    product_price=r["price"],
                    commission_rate=r["commission_rate"],
                    expected_aov=round(aov, 4),
                    cut_threshold=_cut_threshold(aov),
                )
            )

        db.commit()
        return TestBatchUploadResult(
            batch_id=batch.id,
            batch_name=batch_name,
            campaigns_added=len(records),
            message=f"Added {len(records)} campaigns to test batch '{batch_name}'.",
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Batch upload DB error")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    finally:
        db.close()


@router.get("/status", response_model=TestStatusResponse)
def get_test_status():
    db = SessionLocal()
    try:
        campaigns = evaluate_campaigns(db)
        needs_action = sum(
            1 for c in campaigns if c.action in ("cut", "scale_bid", "mature_bid")
        )
        return TestStatusResponse(
            campaigns=campaigns,
            total=len(campaigns),
            needs_action=needs_action,
        )
    finally:
        db.close()


class MarkAppliedRequest(BaseModel):
    action: str  # "cut" | "scale_bid" | "mature_bid"


class MarkAppliedResponse(BaseModel):
    id: int
    last_applied_action: str
    last_applied_at: datetime


@router.post("/campaigns/{campaign_id}/mark-applied", response_model=MarkAppliedResponse)
def mark_action_applied(campaign_id: int, body: MarkAppliedRequest):
    """Mark a recommendation as applied so it stops showing in the action list."""
    if body.action not in {"cut", "scale_bid", "mature_bid"}:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    db = SessionLocal()
    try:
        tc = db.query(TestCampaign).filter(TestCampaign.id == campaign_id).first()
        if tc is None:
            raise HTTPException(status_code=404, detail="Test campaign not found")
        tc.last_applied_action = body.action
        tc.last_applied_at = datetime.utcnow()
        db.commit()
        return MarkAppliedResponse(
            id=tc.id,
            last_applied_action=tc.last_applied_action,
            last_applied_at=tc.last_applied_at,
        )
    finally:
        db.close()


@router.post("/campaigns/{campaign_id}/reset")
def reset_applied(campaign_id: int):
    """Clear the applied marker so the recommendation reappears."""
    db = SessionLocal()
    try:
        tc = db.query(TestCampaign).filter(TestCampaign.id == campaign_id).first()
        if tc is None:
            raise HTTPException(status_code=404, detail="Test campaign not found")
        tc.last_applied_action = None
        tc.last_applied_at = None
        db.commit()
        return {"id": tc.id, "reset": True}
    finally:
        db.close()


@router.get("/export")
def export_google_ads_csv():
    db = SessionLocal()
    try:
        campaigns = evaluate_campaigns(db)
    finally:
        db.close()

    csv_str = build_google_ads_export(campaigns)
    return StreamingResponse(
        io.BytesIO(csv_str.encode("utf-8")),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="google_ads_actions.csv"'
        },
    )

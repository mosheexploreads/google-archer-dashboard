"""
Campaign draft endpoints.

POST /api/campaigns/drafts               — generate attribution links + create drafts
GET  /api/campaigns/drafts               — list drafts
GET  /api/campaigns/export               — download Google Ads Editor CSV
POST /api/campaigns/drafts/{id}/mark-exported — mark a draft as exported
"""
import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models import CampaignDraft
from ..schemas import (
    CampaignDraftRow,
    CampaignDraftsResponse,
    GenerateDraftsRequest,
    GenerateDraftsResponse,
)
from ..services.campaign_service import generate_drafts, build_google_ads_export

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/campaigns")


@router.post("/drafts", response_model=GenerateDraftsResponse)
def create_drafts(body: GenerateDraftsRequest, db: Session = Depends(get_db)):
    if not body.items:
        raise HTTPException(status_code=400, detail="items list is empty")

    for item in body.items:
        if not item.get("asin") or not item.get("country_code"):
            raise HTTPException(status_code=422, detail="Each item must have asin and country_code")

    drafts = generate_drafts(db, body.items)
    return GenerateDraftsResponse(created=len(drafts), drafts=drafts)


@router.get("/drafts", response_model=CampaignDraftsResponse)
def list_drafts(
    country_code: str = "",
    status: str = "",
    db: Session = Depends(get_db),
):
    q = db.query(CampaignDraft)
    if country_code:
        q = q.filter(CampaignDraft.country_code == country_code.upper())
    if status:
        q = q.filter(CampaignDraft.status == status)

    rows = q.order_by(CampaignDraft.created_at.desc()).all()
    drafts = [
        CampaignDraftRow(
            id=r.id,
            asin=r.asin,
            country_code=r.country_code,
            product_name=r.product_name,
            attribution_link=r.attribution_link,
            campaign_name=r.campaign_name,
            suggested_bid=r.suggested_bid,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return CampaignDraftsResponse(drafts=drafts, total=len(drafts))


@router.get("/export")
def export_google_ads_csv(db: Session = Depends(get_db)):
    rows = db.query(CampaignDraft).filter(CampaignDraft.status == "draft").all()
    drafts = [
        CampaignDraftRow(
            id=r.id, asin=r.asin, country_code=r.country_code,
            product_name=r.product_name, attribution_link=r.attribution_link,
            campaign_name=r.campaign_name, suggested_bid=r.suggested_bid,
            status=r.status, created_at=r.created_at,
        )
        for r in rows
    ]
    csv_str = build_google_ads_export(drafts)
    return StreamingResponse(
        io.BytesIO(csv_str.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="campaign_drafts.csv"'},
    )


@router.post("/drafts/{draft_id}/mark-exported")
def mark_exported(draft_id: int, db: Session = Depends(get_db)):
    draft = db.query(CampaignDraft).filter(CampaignDraft.id == draft_id).first()
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.status = "exported"
    db.commit()
    return {"id": draft_id, "status": "exported"}

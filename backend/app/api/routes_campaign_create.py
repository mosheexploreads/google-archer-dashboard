"""
Campaign Creator endpoints.

POST /api/campaign-creator/start          — submit ASINs, kick off background job
GET  /api/campaign-creator/jobs           — list all jobs (most recent first)
GET  /api/campaign-creator/jobs/{job_id}  — live status + item counts
GET  /api/campaign-creator/jobs/{job_id}/download — download Google Ads Editor ZIP
"""
import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CampaignJob, CampaignJobItem
from ..schemas import (
    CampaignCreatorJobStatus,
    CampaignCreatorJobsResponse,
    CampaignCreatorStartRequest,
)
from ..services import campaign_generator
from ..services.csv_builder import build_zip, build_delta_zip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/campaign-creator")


def _job_to_schema(job: CampaignJob, db: Session) -> CampaignCreatorJobStatus:
    """Build a live status schema by counting items directly (avoids race conditions)."""
    done = db.query(CampaignJobItem).filter(
        CampaignJobItem.job_id == job.id,
        CampaignJobItem.status == "done",
    ).count()
    failed = db.query(CampaignJobItem).filter(
        CampaignJobItem.job_id == job.id,
        CampaignJobItem.status == "failed",
    ).count()
    return CampaignCreatorJobStatus(
        job_id=job.id,
        status=job.status,
        campaign_type=job.campaign_type or "brand",
        total=job.total,
        processed=done + failed,
        failed_count=failed,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("/start")
def start_campaign_job(
    body: CampaignCreatorStartRequest,
    db: Session = Depends(get_db),
):
    items = [
        {"asin": i.get("asin", "").strip().upper(), "product_name": i.get("product_name")}
        for i in body.items
        if i.get("asin", "").strip()
    ]
    if not items:
        raise HTTPException(status_code=400, detail="No valid ASINs provided")

    campaign_type = body.campaign_type if body.campaign_type in ("brand", "amazon") else "brand"
    job_id = campaign_generator.start_job(items, campaign_type=campaign_type)
    return {"job_id": job_id, "total": len(items)}


@router.get("/jobs", response_model=CampaignCreatorJobsResponse)
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(CampaignJob).order_by(CampaignJob.created_at.desc()).limit(50).all()
    return CampaignCreatorJobsResponse(jobs=[_job_to_schema(j, db) for j in jobs])


@router.get("/jobs/{job_id}", response_model=CampaignCreatorJobStatus)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(CampaignJob).filter(CampaignJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_schema(job, db)


@router.get("/jobs/{job_id}/items")
def list_job_items(job_id: str, status: str = None, missing_ads: bool = False,
                   db: Session = Depends(get_db)):
    """
    Read-only per-item dump for a job. Used to inspect failures and to
    regenerate ad copy for 'done' items that came back with empty ad_copy.
    Optional filters: status=done|failed, missing_ads=true (done but no headlines).
    """
    import json as _json
    q = db.query(CampaignJobItem).filter(CampaignJobItem.job_id == job_id)
    if status:
        q = q.filter(CampaignJobItem.status == status)
    out = []
    for it in q.all():
        campaign_name, n_head, n_kw = None, 0, 0
        if it.ad_copy:
            try:
                ac = _json.loads(it.ad_copy)
                campaign_name = ac.get("campaign_name")
                n_head = len(ac.get("headlines") or [])
                n_kw = len(ac.get("keywords") or [])
            except Exception:
                pass
        if missing_ads and (it.status != "done" or n_head > 0):
            continue
        out.append({
            "asin": it.asin,
            "product_name": it.product_name,
            "attribution_link": it.attribution_link,
            "campaign_name": campaign_name,
            "n_headlines": n_head,
            "n_keywords": n_kw,
            "status": it.status,
            "error": it.error,
        })
    return {"job_id": job_id, "count": len(out), "items": out}


@router.post("/jobs/{job_id}/regenerate-missing")
def regenerate_missing_ads(job_id: str, db: Session = Depends(get_db)):
    """
    Re-run ad-copy generation for 'done' items with empty ad_copy, preserving
    their existing campaign names + attribution links. Runs in the background;
    poll /jobs/{id}/items?missing_ads=true to watch it drain, then
    GET /jobs/{id}/download-delta for the new keyword + ad rows.
    """
    job = db.query(CampaignJob).filter(CampaignJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    queued = campaign_generator.regenerate_missing_ads(job_id)
    return {"job_id": job_id, "queued": queued}


@router.get("/jobs/{job_id}/download-delta")
def download_delta(job_id: str, db: Session = Depends(get_db)):
    """
    ZIP with only keyword + ad rows for items whose campaigns are ALREADY
    uploaded (fallback-named 'Campaign - ...'). Import on top of existing campaigns.
    """
    import json as _json
    job = db.query(CampaignJob).filter(CampaignJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    items = db.query(CampaignJobItem).filter(
        CampaignJobItem.job_id == job_id,
        CampaignJobItem.status == "done",
    ).all()

    delta = []
    for it in items:
        if not it.ad_copy:
            continue
        try:
            name = _json.loads(it.ad_copy).get("campaign_name") or ""
        except Exception:
            continue
        if name.startswith("Campaign - "):   # fallback-named = campaign already uploaded empty
            delta.append(it)

    if not delta:
        raise HTTPException(status_code=400, detail="No delta items ready (run regenerate-missing first)")

    zip_bytes = build_delta_zip(delta)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="campaigns_{job_id[:8]}_ADS_DELTA.zip"'},
    )


@router.get("/jobs/{job_id}/download")
def download_zip(job_id: str, db: Session = Depends(get_db)):
    job = db.query(CampaignJob).filter(CampaignJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("completed", "partial"):
        raise HTTPException(status_code=400, detail=f"Job is not ready for download (status: {job.status})")

    items = db.query(CampaignJobItem).filter(
        CampaignJobItem.job_id == job_id,
        CampaignJobItem.status == "done",
    ).all()

    if not items:
        raise HTTPException(status_code=400, detail="No completed items to download")

    zip_bytes = build_zip(items)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="campaigns_{job_id[:8]}.zip"'},
    )

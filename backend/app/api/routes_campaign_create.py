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
from ..services.csv_builder import build_zip

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

    job_id = campaign_generator.start_job(items)
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

from datetime import date
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    SummaryResponse, CampaignsResponse, CampaignDatesResponse,
    TimeseriesResponse, WarningsResponse,
)
from ..services.aggregation import (
    get_summary, get_campaigns, get_campaign_dates, get_timeseries, get_warnings,
)
from ..utils.date_utils import yesterday, days_ago

router = APIRouter(prefix="/api/dashboard")

GroupBy = Literal["day", "week", "month"]


def _default_dates(date_from: Optional[date], date_to: Optional[date]):
    if date_to is None:
        date_to = yesterday()
    if date_from is None:
        date_from = days_ago(7)
    return date_from, date_to


@router.get("/summary", response_model=SummaryResponse)
def dashboard_summary(
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    date_from, date_to = _default_dates(date_from, date_to)
    return get_summary(db, date_from, date_to)


@router.get("/campaigns", response_model=CampaignsResponse)
def dashboard_campaigns(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    sort_by: str = Query("spend_usd", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
    asin: str = Query("", description="Filter by ASIN (partial match)"),
    campaign: str = Query("", description="Filter by campaign name (partial match)"),
    status: str = Query("", description="Filter by campaign status (Enabled/Paused/Removed)"),
    db: Session = Depends(get_db),
):
    date_from, date_to = _default_dates(date_from, date_to)
    rows = get_campaigns(
        db, date_from, date_to,
        sort_by=sort_by, sort_dir=sort_dir,
        asin_filter=asin, campaign_filter=campaign,
        status_filter=status,
    )
    return CampaignsResponse(rows=rows, total=len(rows))


@router.get("/campaigns/{campaign_id}/dates", response_model=CampaignDatesResponse)
def dashboard_campaign_dates(
    campaign_id: str,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    groupby: GroupBy = Query("day"),
    db: Session = Depends(get_db),
):
    """Date drill-down for one campaign. Always returns rows in chronological order."""
    date_from, date_to = _default_dates(date_from, date_to)
    dates = get_campaign_dates(db, campaign_id, date_from, date_to, groupby)
    return CampaignDatesResponse(campaign_id=campaign_id, dates=dates)


@router.get("/timeseries", response_model=TimeseriesResponse)
def dashboard_timeseries(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    groupby: GroupBy = Query("day"),
    db: Session = Depends(get_db),
):
    date_from, date_to = _default_dates(date_from, date_to)
    points = get_timeseries(db, date_from, date_to, groupby)
    return TimeseriesResponse(points=points)


@router.get("/warnings", response_model=WarningsResponse)
def dashboard_warnings(db: Session = Depends(get_db)):
    return WarningsResponse(warnings=get_warnings(db))

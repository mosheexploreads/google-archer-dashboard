from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime



# ── Summary ──────────────────────────────────────────────────────────────────

class SummaryResponse(BaseModel):
    spend_usd: float
    revenue_usd: float
    roas: Optional[float]
    rpc: Optional[float]
    acos: Optional[float]
    orders: int
    units_sold: int
    clicks: int
    impressions: int
    date_from: str
    date_to: str


# ── Campaign-level rows (no date dimension) ──────────────────────────────────

class CampaignRow(BaseModel):
    campaign_id: str
    campaign_name: str
    asin: Optional[str]
    product_name: Optional[str]
    impressions: int
    clicks: int
    ctr: Optional[float]
    spend_usd: float
    cpc: Optional[float]
    orders: int
    conv_rate: Optional[float]
    revenue_usd: float
    rpc: Optional[float]
    profit: float
    roas: Optional[float]
    # kept for filtering/export but not displayed in primary columns
    acos: Optional[float]
    units_sold: int
    current_status: Optional[str] = None
    first_seen: Optional[str] = None


class CampaignsResponse(BaseModel):
    rows: List[CampaignRow]
    total: int


# ── Date drill-down rows (per campaign) ──────────────────────────────────────

class DateRow(BaseModel):
    period: str          # "2026-02-18" | "2026-W07" | "2026-02"
    impressions: int
    clicks: int
    ctr: Optional[float]
    spend_usd: float
    cpc: Optional[float]
    orders: int
    conv_rate: Optional[float]
    revenue_usd: float
    rpc: Optional[float]
    profit: float
    roas: Optional[float]
    acos: Optional[float]
    units_sold: int


class CampaignDatesResponse(BaseModel):
    campaign_id: str
    dates: List[DateRow]


# ── Timeseries ────────────────────────────────────────────────────────────────

class TimeseriesPoint(BaseModel):
    period: str
    impressions: int
    clicks: int
    ctr: Optional[float]
    spend_usd: float
    cpc: Optional[float]
    orders: int
    conv_rate: Optional[float]
    revenue_usd: float
    rpc: Optional[float]
    profit: float
    roas: Optional[float]


class TimeseriesResponse(BaseModel):
    points: List[TimeseriesPoint]


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    google_ads_last_sync: Optional[datetime]
    archer_last_sync: Optional[datetime]
    next_scheduled_run: Optional[datetime]
    is_running: bool


class SyncTriggerResponse(BaseModel):
    message: str


# Legacy nested structure matching the frontend SyncStatus type
class SyncSourceStatus(BaseModel):
    source: str
    last_sync: Optional[datetime]
    last_status: Optional[str]
    rows_last_sync: Optional[int]


class SyncStatus(BaseModel):
    google_ads: SyncSourceStatus
    archer: SyncSourceStatus
    next_run: Optional[datetime]
    is_syncing: bool = False


class TriggerResponse(BaseModel):
    message: str


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db_ok: bool
    version: str = "1.0.0"


# ── Warnings ──────────────────────────────────────────────────────────────────

class ProductWarning(BaseModel):
    campaign_name: str
    asin: str
    last_archer_date: str
    days_missing: int


class WarningsResponse(BaseModel):
    warnings: List[ProductWarning]

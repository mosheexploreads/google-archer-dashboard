from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime



# ── Summary ──────────────────────────────────────────────────────────────────

class SummaryResponse(BaseModel):
    spend_usd: float
    revenue_usd: float
    total_sales_usd: float = 0.0
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
    country_code: Optional[str] = "US"
    account: Optional[str] = None
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
    total_sales_usd: float = 0.0
    current_status: Optional[str] = None
    first_seen: Optional[str] = None
    campaign_type: Optional[str] = None  # "brand" | "amazon" | None (legacy)


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
    total_sales_usd: float = 0.0
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
    total_sales_usd: float = 0.0
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
    google_ads_data_through: Optional[str] = None  # latest date in google_ads_campaign_day


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


# ── Detailed export ───────────────────────────────────────────────────────────

class DetailedExportRow(BaseModel):
    campaign_id: str
    campaign_name: str
    asin: Optional[str]
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
    acos: Optional[float]
    units_sold: int


class DetailedExportResponse(BaseModel):
    rows: List[DetailedExportRow]


# ── Testing ───────────────────────────────────────────────────────────────────

class TestBatchUploadResult(BaseModel):
    batch_id: int
    batch_name: str
    campaigns_added: int
    message: str


class TestCampaignStatus(BaseModel):
    id: int
    batch_id: int
    batch_name: str
    campaign_name: str
    asin: Optional[str]
    expected_aov: float
    cut_threshold: int
    clicks: int
    orders: int
    spend_usd: float
    revenue_usd: float
    rpc: Optional[float]
    cpc: Optional[float]
    action: str            # "testing" | "cut" | "scale_bid" | "mature_bid" | "no_data"
    new_bid: Optional[float]
    action_reason: str


class TestStatusResponse(BaseModel):
    campaigns: List[TestCampaignStatus]
    total: int
    needs_action: int


# ── Product Catalog ───────────────────────────────────────────────────────────

class ProductCatalogItem(BaseModel):
    asin: str
    country_code: str
    product_name: Optional[str]
    price: Optional[float]
    rating: Optional[float]
    review_count: Optional[int]
    image_url: Optional[str]
    availability: Optional[str]
    affiliate_url: Optional[str]
    last_synced_at: Optional[datetime]


class ProductCatalogResponse(BaseModel):
    items: List[ProductCatalogItem]
    total: int


class CatalogSyncStatus(BaseModel):
    country_code: str
    last_synced_at: Optional[datetime]
    records: int


class CatalogSyncStatusResponse(BaseModel):
    markets: List[CatalogSyncStatus]


# ── Campaign Drafts ───────────────────────────────────────────────────────────

class CampaignDraftRow(BaseModel):
    id: int
    asin: str
    country_code: str
    product_name: Optional[str]
    attribution_link: Optional[str]
    campaign_name: str
    suggested_bid: float
    status: str
    created_at: Optional[datetime]


class CampaignDraftsResponse(BaseModel):
    drafts: List[CampaignDraftRow]
    total: int


class GenerateDraftsRequest(BaseModel):
    items: List[dict]  # [{asin, country_code}, ...]


class GenerateDraftsResponse(BaseModel):
    created: int
    drafts: List[CampaignDraftRow]


# ── Campaign Creator (ASIN → ad copy → Google Ads ZIP) ───────────────────────

class CampaignCreatorStartRequest(BaseModel):
    items: List[dict]  # [{asin: str, product_name: str | None}, ...]
    campaign_type: str = "brand"  # "brand" | "amazon"


class CampaignCreatorJobStatus(BaseModel):
    job_id: str
    status: str   # pending | running | completed | partial | failed
    campaign_type: str = "brand"  # "brand" | "amazon"
    total: int
    processed: int
    failed_count: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class CampaignCreatorItemStatus(BaseModel):
    id: int
    asin: str
    product_name: Optional[str]
    attribution_link: Optional[str]
    status: str   # pending | done | failed
    error: Optional[str]


class CampaignCreatorJobsResponse(BaseModel):
    jobs: List[CampaignCreatorJobStatus]

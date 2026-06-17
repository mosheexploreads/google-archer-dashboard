from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from .database import Base


class GoogleAdsCampaignDay(Base):
    """One row per (campaign_id, date). Upserted on each sync."""
    __tablename__ = "google_ads_campaign_day"

    campaign_id = Column(String, primary_key=True, nullable=False)
    date = Column(Date, primary_key=True, nullable=False)
    campaign_name = Column(String, nullable=False)
    asin = Column(String, nullable=True, index=True)  # extracted at insert time
    country_code = Column(String, nullable=True, index=True)  # e.g. "UK", "DE"; None = US
    account = Column(String, nullable=True, index=True)  # which Google Ads account (label set at CSV upload)

    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend_usd = Column(Float, default=0.0)
    campaign_status = Column(String, nullable=True)
    campaign_type = Column(String, nullable=True)  # "brand" | "amazon" | None (legacy)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ArcherProductDay(Base):
    """One row per (asin, date, geo, link_type, source). Upserted on each sync."""
    __tablename__ = "archer_product_day"

    asin = Column(String, primary_key=True, nullable=False)
    date = Column(Date, primary_key=True, nullable=False)
    geo = Column(String, primary_key=True, nullable=False, default="US")  # US | EU | FE | CA
    link_type = Column(String, primary_key=True, nullable=False, default="brand")  # "brand" | "amazon"
    # Which Archer API produced the row. "legacy" = deprecated /product_reports_all,
    # "new" = /reports v2 (link-attributed direct+halo). Both are synced and kept.
    source = Column(String, primary_key=True, nullable=False, default="legacy")
    product_name = Column(String, nullable=True)

    revenue_usd     = Column(Float, default=0.0)
    total_sales_usd = Column(Float, default=0.0)  # Amazon gross sales (not just commission)
    orders          = Column(Integer, default=0)
    units_sold      = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ArcherLinkProductDay(Base):
    """
    Per-product breakdown from the NEW /reports v2 API: which ASIN actually sold
    under a given campaign link, per day. `link_asin` is the ASIN the link was
    created for (= the campaign's ASIN); `sold_asin` is the product actually
    purchased. When they differ, that's a halo sale. Only sales-bearing rows are
    stored (new source only — legacy can't report this).
    """
    __tablename__ = "archer_link_product_day"

    link_asin  = Column(String, primary_key=True, nullable=False)   # the campaign's ASIN
    link_type  = Column(String, primary_key=True, nullable=False, default="brand")  # brand|amazon
    sold_asin  = Column(String, primary_key=True, nullable=False)   # ASIN actually purchased
    date       = Column(Date,   primary_key=True, nullable=False)
    geo        = Column(String, primary_key=True, nullable=False, default="US")

    sold_product_name = Column(String, nullable=True)
    brand_name        = Column(String, nullable=True)
    sales             = Column(Float, default=0.0)
    commission        = Column(Float, default=0.0)
    units             = Column(Integer, default=0)
    purchases         = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ProductCatalog(Base):
    """One row per (asin, country_code). Synced from Archer /getproducts."""
    __tablename__ = "product_catalog"

    asin = Column(String, primary_key=True, nullable=False)
    country_code = Column(String, primary_key=True, nullable=False)  # e.g. "UK", "DE", "JP"
    product_name = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    image_url = Column(String, nullable=True)
    availability = Column(String, nullable=True)
    affiliate_url = Column(String, nullable=True)
    last_synced_at = Column(DateTime, server_default=func.now())


class CampaignDraft(Base):
    """One row per campaign ready to be imported into Google Ads."""
    __tablename__ = "campaign_draft"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asin = Column(String, nullable=False, index=True)
    country_code = Column(String, nullable=False)  # e.g. "UK"
    product_name = Column(String, nullable=True)
    attribution_link = Column(String, nullable=True)
    campaign_name = Column(String, nullable=False)
    suggested_bid = Column(Float, default=0.50)
    status = Column(String, nullable=False, default="draft")  # draft | exported
    created_at = Column(DateTime, server_default=func.now())


class TestBatch(Base):
    """One row per uploaded batch CSV of campaigns to test."""
    __tablename__ = "test_batch"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    uploaded_at = Column(DateTime, server_default=func.now())
    campaign_count = Column(Integer, default=0)


class TestCampaign(Base):
    """One row per campaign in a test batch."""
    __tablename__ = "test_campaign"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("test_batch.id"), nullable=False)
    campaign_name = Column(String, nullable=False, index=True)
    asin = Column(String, nullable=True, index=True)
    product_price = Column(Float, nullable=False)
    commission_rate = Column(Float, nullable=False)
    expected_aov = Column(Float, nullable=False)   # price × commission_rate
    cut_threshold = Column(Integer, nullable=False) # 30 / 60 / 100 by AOV tier
    added_at = Column(DateTime, server_default=func.now())

    # Tracking when a recommendation has been acted on. Cleared if a new
    # recommendation type fires later (e.g., scale → mature).
    last_applied_action = Column(String, nullable=True)   # "cut" | "scale_bid" | "mature_bid"
    last_applied_at = Column(DateTime, nullable=True)


class ArcherAsinStatus(Base):
    """Per-ASIN verification result from /get_single_product. Updated daily."""
    __tablename__ = "archer_asin_status"

    asin = Column(String, primary_key=True, nullable=False)
    is_active = Column(Integer, nullable=False, default=1)  # 1 = active, 0 = removed
    product_name = Column(String, nullable=True)
    last_checked_at = Column(DateTime, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # first time we detected removal


class AttributionLinkCache(Base):
    """Cached Archer attribution links keyed by (asin, campaign_type)."""
    __tablename__ = "attribution_link_cache"

    asin = Column(String, primary_key=True, nullable=False)
    campaign_type = Column(String, primary_key=True, nullable=False, default="brand")  # "brand" | "amazon"
    url = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class CampaignJob(Base):
    """One row per campaign-generation batch submitted by the user."""
    __tablename__ = "campaign_job"

    id = Column(String, primary_key=True, nullable=False)  # UUID
    status = Column(String, nullable=False, default="pending")  # pending|running|completed|partial|failed
    campaign_type = Column(String, nullable=False, default="brand")  # "brand" | "amazon"
    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    settings = Column(Text, nullable=True)  # reserved JSON
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CampaignJobItem(Base):
    """One row per ASIN in a campaign job."""
    __tablename__ = "campaign_job_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("campaign_job.id"), nullable=False, index=True)
    asin = Column(String, nullable=False)
    product_name = Column(String, nullable=True)
    attribution_link = Column(String, nullable=True)
    ad_copy = Column(Text, nullable=True)   # JSON: {campaign_name, keywords, headlines, descriptions}
    status = Column(String, nullable=False, default="pending")  # pending|done|failed
    error = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DiscoveryScan(Base):
    """
    One row per discovery session. Two independent phases:
      Phase 1 (Archer) — fetch catalog, filter by rating/reviews → fast
      Phase 2 (Rainforest) — check BSR for filtered ASINs → slow, costs API credits
    """
    __tablename__ = "discovery_scan"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Phase 1: Archer catalog scan ──────────────────────────────────────────
    archer_status = Column(String, nullable=False, default="idle")  # idle|running|complete|error
    min_rating = Column(Float, default=4.2)
    min_reviews = Column(Integer, default=100)
    result_limit = Column(Integer, default=1000)  # stop after N qualifying products found
    total_archer = Column(Integer, default=0)     # total products scanned from Archer (may stop early)
    total_filtered = Column(Integer, default=0)   # passed rating/review filter
    archer_started_at = Column(DateTime, nullable=True)
    archer_finished_at = Column(DateTime, nullable=True)
    archer_error = Column(Text, nullable=True)

    # ── Phase 2: Rainforest ranking check ────────────────────────────────────
    rank_status = Column(String, nullable=False, default="idle")  # idle|running|complete|error
    max_rank = Column(Integer, default=5)
    total_ranked = Column(Integer, default=0)    # ASINs checked via Rainforest
    total_found = Column(Integer, default=0)     # passed rank filter
    rank_started_at = Column(DateTime, nullable=True)
    rank_finished_at = Column(DateTime, nullable=True)
    rank_error = Column(Text, nullable=True)


class DiscoveryCandidate(Base):
    """Products that passed the Archer filter (Phase 1). Input to Phase 2."""
    __tablename__ = "discovery_candidate"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("discovery_scan.id"), nullable=False, index=True)
    asin = Column(String, nullable=False, index=True)
    product_name = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    price = Column(Float, nullable=True)
    image_url = Column(String, nullable=True)
    affiliate_url = Column(String, nullable=True)
    has_campaign = Column(Integer, default=0)


class DiscoveryResult(Base):
    """Products that passed Phase 2 — top N in their Amazon subcategory."""
    __tablename__ = "discovery_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("discovery_scan.id"), nullable=False, index=True)
    asin = Column(String, nullable=False, index=True)
    product_name = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    price = Column(Float, nullable=True)
    image_url = Column(String, nullable=True)
    affiliate_url = Column(String, nullable=True)
    subcategory = Column(String, nullable=True)
    rank = Column(Integer, nullable=True)
    has_campaign = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class SyncLog(Base):
    """Tracks each sync attempt."""
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)        # "google_ads" | "archer"
    status = Column(String, nullable=False)        # "success" | "error" | "skipped"
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    records_upserted = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

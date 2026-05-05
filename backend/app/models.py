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

    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend_usd = Column(Float, default=0.0)
    campaign_status = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ArcherProductDay(Base):
    """One row per (asin, date). Upserted on each sync."""
    __tablename__ = "archer_product_day"

    asin = Column(String, primary_key=True, nullable=False)
    date = Column(Date, primary_key=True, nullable=False)
    product_name = Column(String, nullable=True)

    revenue_usd = Column(Float, default=0.0)
    orders = Column(Integer, default=0)
    units_sold = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


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

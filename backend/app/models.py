from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text
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

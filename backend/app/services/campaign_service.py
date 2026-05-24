"""
Campaign draft service.

Generates Archer attribution links per (asin, country_code), stores drafts,
and builds a Google Ads Editor-compatible CSV for bulk import.
"""
import csv
import io
import logging
from typing import List

from sqlalchemy.orm import Session

from ..models import CampaignDraft, ProductCatalog
from ..schemas import CampaignDraftRow
from .archer_client import ArcherClient
from ..utils.geo_utils import country_to_geo

logger = logging.getLogger(__name__)

_DEFAULT_BID = 0.50


def generate_drafts(db: Session, items: List[dict]) -> List[CampaignDraftRow]:
    """
    For each {asin, country_code} in items:
    - Look up product name from catalog (if available)
    - Generate an Archer attribution link
    - Store as CampaignDraft with status='draft'
    Returns the created draft rows.
    """
    client = ArcherClient()
    created: List[CampaignDraftRow] = []

    for item in items:
        asin = item.get("asin", "").upper()
        country_code = item.get("country_code", "").upper()
        if not asin or not country_code:
            continue

        # Look up product name from catalog
        catalog_row = (
            db.query(ProductCatalog)
            .filter(ProductCatalog.asin == asin, ProductCatalog.country_code == country_code)
            .first()
        )
        product_name = catalog_row.product_name if catalog_row else None

        # Build campaign name following "Product Name - ASIN - COUNTRY" convention
        name_prefix = product_name[:40].strip() if product_name else asin
        campaign_name = f"{name_prefix} - {asin} - {country_code}"

        # Generate attribution link (non-fatal if it fails)
        geo = country_to_geo(country_code)
        attribution_link: str | None = None
        try:
            attribution_link = client.generate_attribution_link(
                asin=asin,
                link_name=campaign_name,
                geo=geo,
            )
        except Exception as exc:
            logger.warning("Attribution link failed for %s/%s: %s", asin, country_code, exc)

        draft = CampaignDraft(
            asin=asin,
            country_code=country_code,
            product_name=product_name,
            attribution_link=attribution_link,
            campaign_name=campaign_name,
            suggested_bid=_DEFAULT_BID,
            status="draft",
        )
        db.add(draft)
        db.flush()  # populate id

        created.append(
            CampaignDraftRow(
                id=draft.id,
                asin=draft.asin,
                country_code=draft.country_code,
                product_name=draft.product_name,
                attribution_link=draft.attribution_link,
                campaign_name=draft.campaign_name,
                suggested_bid=draft.suggested_bid,
                status=draft.status,
                created_at=draft.created_at,
            )
        )

    db.commit()
    return created


def build_google_ads_export(drafts: List[CampaignDraftRow]) -> str:
    """
    Build a Google Ads Editor bulk CSV from campaign drafts.
    Only includes drafts with status='draft' that have an attribution link.
    Columns: Campaign, Final URL, Campaign bid strategy max. CPC bid limit
    """
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Campaign", "Final URL", "Campaign bid strategy max. CPC bid limit"])

    for d in drafts:
        if d.status != "draft":
            continue
        writer.writerow([
            d.campaign_name,
            d.attribution_link or "",
            f"{d.suggested_bid:.2f}",
        ])

    return out.getvalue()

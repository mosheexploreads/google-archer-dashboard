"""
Google Ads API client wrapper.

Fetches campaign-level metrics for a single date using the google-ads library.
Credentials are read from google-ads.yaml (standard library convention).
"""
import logging
from datetime import date
from typing import List, Dict, Any

from ..config import get_settings

logger = logging.getLogger(__name__)


class GoogleAdsClient:
    def __init__(self):
        self._settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.ads.googleads.client import GoogleAdsClient as _Client
                self._client = _Client.load_from_storage()  # reads google-ads.yaml
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to initialise Google Ads client: {exc}. "
                    "Ensure google-ads.yaml exists with valid credentials."
                ) from exc
        return self._client

    def fetch_campaign_stats(self, report_date: date) -> List[Dict[str, Any]]:
        """
        Fetch impressions, clicks, cost for all campaigns on report_date.
        Returns a list of dicts with keys:
            campaign_id, campaign_name, impressions, clicks, spend_usd
        """
        client = self._get_client()
        customer_id = self._settings.google_ads_customer_id.replace("-", "")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros
            FROM campaign
            WHERE segments.date = '{report_date}'
              AND campaign.status != 'REMOVED'
            ORDER BY campaign.id
        """

        ga_service = client.get_service("GoogleAdsService")
        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        results = []
        for batch in stream:
            for row in batch.results:
                results.append({
                    "campaign_id":   str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "impressions":   row.metrics.impressions,
                    "clicks":        row.metrics.clicks,
                    # cost_micros → USD
                    "spend_usd":     row.metrics.cost_micros / 1_000_000,
                })

        logger.info(
            "Google Ads: fetched %d campaign rows for %s", len(results), report_date
        )
        return results

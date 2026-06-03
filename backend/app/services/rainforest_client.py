"""
Rainforest API client — fetches Amazon product data including Best Sellers Rank.
Docs: https://www.rainforestapi.com/docs/product-data-api/overview
"""
import logging
from typing import Optional, List, Dict, Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.rainforestapi.com/request"


class RainforestClient:
    def __init__(self):
        self._api_key = get_settings().rainforest_api_key
        if not self._api_key:
            raise RuntimeError("RAINFOREST_API_KEY is not configured")

    def get_product(self, asin: str, amazon_domain: str = "amazon.com") -> Dict[str, Any]:
        """
        Fetch full product data for an ASIN.
        Returns the raw Rainforest API response dict.
        Raises httpx.HTTPError on non-2xx responses.
        """
        resp = httpx.get(
            _BASE_URL,
            params={
                "api_key":        self._api_key,
                "type":           "product",
                "asin":           asin,
                "amazon_domain":  amazon_domain,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_bestsellers_rank(self, asin: str) -> List[Dict[str, Any]]:
        """
        Return the bestsellers_rank list for an ASIN.
        Each entry: {"category": str, "rank": int, "link": str}
        Returns [] if the product has no BSR data or the call fails.
        """
        try:
            data = self.get_product(asin)
            product = data.get("product") or {}
            return product.get("bestsellers_rank") or []
        except Exception as exc:
            logger.warning("Rainforest BSR lookup failed for %s: %s", asin, exc)
            return []

    def get_top_subcategory_rank(self, asin: str, max_rank: int) -> Optional[Dict[str, Any]]:
        """
        Return the best (lowest rank number) subcategory entry where rank <= max_rank,
        or None if the product doesn't qualify.

        Returned dict: {"category": str, "rank": int}
        """
        bsr = self.get_bestsellers_rank(asin)
        qualifying = [e for e in bsr if isinstance(e.get("rank"), int) and e["rank"] <= max_rank]
        if not qualifying:
            return None
        return min(qualifying, key=lambda e: e["rank"])

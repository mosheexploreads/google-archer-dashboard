"""
Archer Affiliates HTTP client.

Auth:   POST /token (OAuth2 password flow) → Bearer JWT
Report: GET /product_reports_all with YYYYMMDD dates and page/limit pagination
"""
import logging
from datetime import date
from typing import Optional, List, Dict, Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

# Canonical field → list of possible key names in the API response
_FIELD_ALIASES: Dict[str, List[str]] = {
    "asin":         ["asin", "ASIN", "product_asin", "item_asin"],
    "product_name": ["product_name", "title", "name", "product_title", "item_name", "Product_Name"],
    "revenue_usd":  [
        "commission_amount",
        "Total_Commission", "total_commission",
        "earnings", "revenue_usd", "revenue",
    ],
    "orders":       [
        "total_purchases", "Attributed_Total_Purchases", "attributed_total_purchases",
        "orders", "order_count", "total_orders", "purchases",
    ],
    "units_sold":   [
        "total_units_sold", "Total_Units_Sold",
        "units_sold", "units", "quantity", "qty",
    ],
    "date":         ["date", "Date", "report_date", "day", "order_date", "Day"],
}


def _resolve_field(row: Dict[str, Any], canonical: str, default=None):
    """Return first matching alias value from row, or default."""
    for alias in _FIELD_ALIASES.get(canonical, [canonical]):
        if alias in row:
            return row[alias]
    return default


class ArcherClient:
    def __init__(self):
        self._settings = get_settings()
        self._base_url = self._settings.archer_base_url.rstrip("/")

    def _get_token(self, client: httpx.Client) -> str:
        """POST /token to obtain a Bearer JWT."""
        resp = client.post(
            f"{self._base_url}/token",
            data={
                "username": self._settings.archer_username,
                "password": self._settings.archer_password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError(f"No access_token in /token response: {resp.text[:200]}")
        logger.info("Archer: token obtained successfully")
        return token

    def fetch_earnings(self, date_from: date, date_to: date) -> List[Dict[str, Any]]:
        """
        Fetch per-product daily earnings for date_from..date_to.
        Handles pagination automatically (API max 100 rows/page).
        Returns list of normalised dicts with keys:
          asin, product_name, revenue_usd, orders, units_sold, date
        """
        start_str = date_from.strftime("%Y%m%d")
        end_str   = date_to.strftime("%Y%m%d")
        all_rows: List[Dict] = []

        with httpx.Client() as client:
            token = self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            page = 1
            limit = 100
            while True:
                resp = client.get(
                    f"{self._base_url}/product_reports_all",
                    params={
                        "start_date": start_str,
                        "end_date":   end_str,
                        "page":       page,
                        "limit":      limit,
                    },
                    headers=headers,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                # Accept list or wrapped {"data": [...]} shapes
                if isinstance(data, list):
                    rows = data
                else:
                    rows = next(
                        (data[k] for k in ("data", "results", "rows", "items", "records")
                         if k in data and isinstance(data[k], list)),
                        []
                    )

                if not rows:
                    break

                # Log first row keys once so we can verify field mapping
                if page == 1:
                    logger.info(
                        "Archer /product_reports_all page 1: %d rows, fields: %s",
                        len(rows), list(rows[0].keys()) if rows else []
                    )

                all_rows.extend(rows)

                if len(rows) < limit:
                    break  # last page
                page += 1

        logger.info(
            "Archer: fetched %d total rows for %s – %s (%d pages)",
            len(all_rows), date_from, date_to, page,
        )

        # Normalise field names
        normalised = []
        for row in all_rows:
            normalised.append({
                "asin":         _resolve_field(row, "asin"),
                "product_name": _resolve_field(row, "product_name"),
                "revenue_usd":  float(_resolve_field(row, "revenue_usd") or 0),
                "orders":       int(_resolve_field(row, "orders") or 0),
                "units_sold":   int(_resolve_field(row, "units_sold") or 0),
                "date":         _resolve_field(row, "date"),
            })
        return normalised

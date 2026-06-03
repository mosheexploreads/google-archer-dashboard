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
    "asin":             ["asin", "ASIN", "product_asin", "item_asin"],
    "product_name":     ["product_name", "title", "name", "product_title", "item_name", "Product_Name"],
    "revenue_usd":      [
        "commission_amount",
        "Total_Commission", "total_commission",
        "earnings", "revenue_usd", "revenue",
    ],
    "total_sales_usd":  [
        "total_sales", "Total_Sales",
        "attributed_sales", "total_attributed_sales",
        "gross_sales", "sales_usd",
    ],
    "orders":           [
        "total_purchases", "Attributed_Total_Purchases", "attributed_total_purchases",
        "orders", "order_count", "total_orders", "purchases",
    ],
    "units_sold":       [
        "total_units_sold", "Total_Units_Sold",
        "units_sold", "units", "quantity", "qty",
    ],
    "date":             ["date", "Date", "report_date", "day", "order_date", "Day"],
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

    def fetch_earnings(self, date_from: date, date_to: date, geo: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch per-product daily earnings for date_from..date_to.
        Pass geo="EU" or geo="FE" for non-US markets; omit for US.
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
                params: Dict[str, Any] = {
                    "start_date": start_str,
                    "end_date":   end_str,
                    "page":       page,
                    "limit":      limit,
                }
                if geo:
                    params["geo"] = geo
                resp = client.get(
                    f"{self._base_url}/product_reports_all",
                    params=params,
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
            # Classify link type from link_name: "Google Ads - ASIN - Amazon" → "amazon",
            # everything else (e.g. "Campaign_ASIN") → "brand".
            link_name = str(row.get("link_name") or "")
            link_type = "amazon" if "amazon" in link_name.lower() else "brand"
            normalised.append({
                "asin":             _resolve_field(row, "asin"),
                "product_name":     _resolve_field(row, "product_name"),
                "revenue_usd":      float(_resolve_field(row, "revenue_usd") or 0),
                "total_sales_usd":  float(_resolve_field(row, "total_sales_usd") or 0),
                "orders":           int(_resolve_field(row, "orders") or 0),
                "units_sold":       int(_resolve_field(row, "units_sold") or 0),
                "date":             _resolve_field(row, "date"),
                "link_type":        link_type,
            })
        return normalised

    def fetch_products_paged(self, country_code: str):
        """
        Generator — yields one page (list of raw dicts) at a time.
        Lets callers stop early without fetching the entire catalog.
        """
        with httpx.Client() as client:
            token = self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            skip = 0
            limit = 100
            page_num = 0
            while True:
                resp = client.get(
                    f"{self._base_url}/getproducts",
                    params={"country_code": country_code, "skip": skip, "limit": limit},
                    headers=headers,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, list):
                    rows = data
                else:
                    rows = next(
                        (data[k] for k in ("product_catalog", "data", "results", "rows", "items", "products")
                         if k in data and isinstance(data[k], list)),
                        []
                    )

                if not rows:
                    break

                if page_num == 0:
                    logger.info(
                        "Archer /getproducts [%s] first page: %d rows, fields: %s",
                        country_code, len(rows), list(rows[0].keys()) if rows else [],
                    )

                yield rows

                if len(rows) < limit:
                    break
                skip += len(rows)
                page_num += 1

    def fetch_products(self, country_code: str) -> List[Dict[str, Any]]:
        """
        Fetch product catalog for a given country code via GET /getproducts.
        Returns normalised dicts with keys:
          asin, product_name, price, rating, review_count, image_url, availability, affiliate_url
        """
        all_rows: List[Dict] = []

        with httpx.Client() as client:
            token = self._get_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            skip = 0
            limit = 100
            while True:
                resp = client.get(
                    f"{self._base_url}/getproducts",
                    params={
                        "country_code": country_code,
                        "skip":  skip,
                        "limit": limit,
                    },
                    headers=headers,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, list):
                    rows = data
                else:
                    rows = next(
                        (data[k] for k in ("product_catalog", "data", "results", "rows", "items", "products")
                         if k in data and isinstance(data[k], list)),
                        []
                    )

                if not rows:
                    break

                if skip == 0:
                    logger.info(
                        "Archer /getproducts [%s] first batch: %d rows, total=%s, fields: %s",
                        country_code, len(rows), data.get("total_count", "?"),
                        list(rows[0].keys()) if rows else []
                    )

                all_rows.extend(rows)
                if len(rows) < limit:
                    break
                skip += len(rows)

        logger.info("Archer: fetched %d products for %s", len(all_rows), country_code)

        normalised = []
        for row in all_rows:
            asin = row.get("ASIN") or row.get("asin") or row.get("product_asin")
            if not asin:
                continue
            normalised.append({
                "asin":          str(asin).upper(),
                "product_name":  row.get("product_name") or row.get("title") or row.get("name"),
                "price":         _safe_num(row.get("price") or row.get("product_price")),
                "rating":        _safe_num(row.get("avg_rating") or row.get("average_rating") or row.get("rating")),
                "review_count":  _safe_int(row.get("total_reviews") or row.get("review_count") or row.get("reviews")),
                "image_url":     row.get("image_encoded_string") or row.get("image_url") or row.get("image") or row.get("thumbnail"),
                "availability":  row.get("product_status") or row.get("availability") or row.get("status"),
                "affiliate_url": row.get("affiliate_url") or row.get("url") or row.get("link"),
            })
        return normalised

    def check_asin(self, asin: str) -> dict:
        """
        Check whether an ASIN is still active in Archer via GET /get_single_product.
        Returns {"is_active": bool, "product_name": str|None}.
        """
        with httpx.Client() as client:
            token = self._get_token(client)
            resp = client.get(
                f"{self._base_url}/get_single_product",
                params={"asin": asin},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "is_active": True,
                "product_name": data.get("product_name") or data.get("PRODUCT_NAME"),
            }
        # 500 with "ASIN not found" means removed; treat any non-200 as removed
        return {"is_active": False, "product_name": None}

    def generate_attribution_link(self, asin: str, link_name: str, geo: str) -> Optional[str]:
        """
        Call POST /generate_attribution_link and return the attribution URL.
        Returns None if the API call fails (logged as warning, not raised).
        """
        with httpx.Client() as client:
            token = self._get_token(client)
            resp = client.post(
                f"{self._base_url}/generate_attribution_link",
                json={"asin": asin, "link_name": link_name, "geo": geo},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            url = (
                data.get("attribution_link")
                or data.get("attribution_url")
                or data.get("url")
                or data.get("link")
                or data.get("tracking_url")
            )
            if not url:
                logger.warning("generate_attribution_link: no URL in response for %s/%s: %s", asin, geo, data)
            return url


def _safe_num(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None

"""
Archer web portal scraper.

Logs into https://app.archeraffiliates.com/auth/sign-in with username/password,
then navigates to /reports, iterates through each day in the requested range
(changing the date picker each time since the portal has no bulk date drill-down),
and extracts the ASIN-level revenue table.

Returns normalized dicts matching the archer_product_day schema.
"""
import logging
import time
from datetime import date, timedelta
from typing import Optional

from ..config import get_settings
from ..utils.date_utils import date_range

logger = logging.getLogger(__name__)
settings = get_settings()

LOGIN_URL   = "https://app.archeraffiliates.com/auth/sign-in"
REPORTS_URL = "https://app.archeraffiliates.com/reports"


def _login(page) -> None:
    """Log into the Archer portal. Raises RuntimeError on failure."""
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)

    # Fill credentials
    page.fill('input[type="text"]',     settings.archer_username)
    page.fill('input[type="password"]', settings.archer_password)
    page.click('button[type="submit"]')

    # Wait for redirect away from the sign-in page
    try:
        page.wait_for_url(
            lambda url: "sign-in" not in url,
            timeout=15000,
        )
    except Exception:
        # Check for error message
        body_text = page.inner_text("body")
        raise RuntimeError(f"Archer login failed. Page says: {body_text[:200]}")

    logger.info("Archer scraper: logged in successfully. URL: %s", page.url)


def _set_date_range(page, report_date: date) -> bool:
    """
    Set the reports page to show a single day. Returns True on success.
    Tries common date-picker patterns used in Next.js dashboards.
    """
    iso = report_date.isoformat()        # YYYY-MM-DD
    us  = report_date.strftime("%m/%d/%Y")  # MM/DD/YYYY

    # Look for date input fields (type=date or labelled start/end)
    for selector in [
        'input[type="date"]',
        'input[placeholder*="date" i]',
        'input[placeholder*="from" i]',
        'input[name*="start" i]',
        'input[name*="from" i]',
        'input[aria-label*="start" i]',
        'input[aria-label*="from" i]',
    ]:
        els = page.query_selector_all(selector)
        if els:
            # Set start = end = report_date
            for el in els[:2]:
                el.fill("")
                el.type(iso)
                el.dispatch_event("change")
                time.sleep(0.2)

            # Also try the US format in case the field rejects ISO
            if not els[0].input_value():
                els[0].fill(us)
                els[0].dispatch_event("change")

            # Click apply/search button if present
            for btn_text in ["apply", "search", "filter", "go", "submit", "update"]:
                btn = page.query_selector(f'button:has-text("{btn_text}")')
                if btn:
                    btn.click()
                    time.sleep(1)
                    break

            page.wait_for_load_state("networkidle", timeout=10000)
            return True

    return False


def _extract_table(page, report_date: date) -> list[dict]:
    """
    Extract all rows from the reports table on the current page.
    Tries to find ASIN, product name, revenue, orders columns.
    """
    rows = []

    # Find all tables on the page
    tables = page.query_selector_all("table")
    if not tables:
        # Try div-based tables (common in React dashboards)
        logger.warning("Archer scraper: no <table> found on reports page for %s", report_date)
        return rows

    for table in tables:
        headers_els = table.query_selector_all("th")
        if not headers_els:
            headers_els = table.query_selector_all("thead td")
        headers = [h.inner_text().strip().lower() for h in headers_els]
        if not headers:
            continue

        # Find column indices
        def col(*names):
            for name in names:
                for i, h in enumerate(headers):
                    if name in h:
                        return i
            return None

        asin_col     = col("asin")
        name_col     = col("product", "name", "title")
        revenue_col  = col("revenue", "sales", "earnings", "commission")
        orders_col   = col("order", "purchase", "conversion")
        units_col    = col("unit", "qty", "quantity")

        if asin_col is None and revenue_col is None:
            continue  # Not the data table we want

        data_rows = table.query_selector_all("tbody tr")
        for tr in data_rows:
            cells = tr.query_selector_all("td")
            if not cells:
                continue

            def cell_text(idx) -> str:
                if idx is None or idx >= len(cells):
                    return ""
                return cells[idx].inner_text().strip()

            def parse_num(s: str) -> float:
                s = s.replace(",", "").replace("$", "").replace("%", "").strip()
                try:
                    return float(s)
                except ValueError:
                    return 0.0

            asin = cell_text(asin_col).upper() if asin_col is not None else ""
            if not asin or len(asin) < 10:
                continue

            rows.append({
                "asin":         asin,
                "product_name": cell_text(name_col) or None,
                "date":         report_date,
                "revenue_usd":  parse_num(cell_text(revenue_col)),
                "orders":       int(parse_num(cell_text(orders_col))),
                "units_sold":   int(parse_num(cell_text(units_col))),
            })

    logger.info("Archer scraper: extracted %d rows for %s", len(rows), report_date)
    return rows


def _capture_api_responses(page, report_date: date) -> list[dict]:
    """
    Intercept XHR/fetch responses from the reports page — often faster/more
    reliable than parsing the rendered HTML table.
    """
    captured: list[dict] = []

    def handle_response(response):
        if response.status != 200:
            return
        url = response.url
        if not any(k in url for k in ["report", "earning", "stat", "product", "revenue"]):
            return
        try:
            body = response.json()
        except Exception:
            return
        # Flatten list or dict responses
        items = body if isinstance(body, list) else body.get("data") or body.get("results") or []
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            asin = (item.get("asin") or "").strip().upper()
            if not asin:
                continue
            # Try to get the date from the item, fall back to report_date
            item_date = report_date
            for d_field in ["date", "report_date", "day"]:
                if d_field in item:
                    try:
                        from datetime import datetime
                        item_date = datetime.strptime(str(item[d_field])[:10], "%Y-%m-%d").date()
                        break
                    except Exception:
                        pass
            captured.append({
                "asin":         asin,
                "product_name": item.get("product_name") or item.get("name") or None,
                "date":         item_date,
                "revenue_usd":  float(item.get("total_sales") or item.get("revenue") or item.get("earnings") or 0),
                "orders":       int(item.get("total_purchases") or item.get("orders") or 0),
                "units_sold":   int(item.get("total_units_sold") or item.get("units") or 0),
            })
        if captured:
            logger.info("Archer scraper: intercepted %d API rows for %s from %s", len(captured), report_date, url)

    page.on("response", handle_response)
    return captured


def scrape(date_from: date, date_to: date) -> list[dict]:
    """
    Main entry point. Logs in, iterates each day in the range, returns all rows.
    """
    from playwright.sync_api import sync_playwright

    all_rows: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            _login(page)

            # Navigate to reports once
            page.goto(REPORTS_URL, wait_until="networkidle", timeout=20000)
            logger.info("Archer scraper: on reports page. URL: %s", page.url)

            dates = list(date_range(date_from, date_to))
            logger.info("Archer scraper: scraping %d days (%s – %s)", len(dates), date_from, date_to)

            for report_date in dates:
                # Set up response interception for this date
                intercepted: list[dict] = []
                page.on("response", lambda r, d=report_date: intercepted.extend(
                    _capture_api_responses_single(r, d)
                ))

                # Attempt to set date range
                date_set = _set_date_range(page, report_date)
                if not date_set:
                    logger.warning("Archer scraper: could not set date for %s, loading page as-is", report_date)
                    page.reload(wait_until="networkidle", timeout=15000)

                time.sleep(1.5)  # let dynamic content render

                # Try intercepted API data first (more reliable)
                if intercepted:
                    all_rows.extend(intercepted)
                else:
                    # Fall back to HTML table parsing
                    html_rows = _extract_table(page, report_date)
                    all_rows.extend(html_rows)

        finally:
            browser.close()

    logger.info("Archer scraper: total %d rows collected for %s – %s", len(all_rows), date_from, date_to)
    return all_rows


def _capture_api_responses_single(response, report_date: date) -> list[dict]:
    """Helper used in the per-date loop closure."""
    if response.status != 200:
        return []
    url = response.url
    if not any(k in url for k in ["report", "earning", "stat", "product", "revenue", "data"]):
        return []
    try:
        body = response.json()
    except Exception:
        return []
    items = body if isinstance(body, list) else body.get("data") or body.get("results") or []
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        asin = (item.get("asin") or "").strip().upper()
        if not asin:
            continue
        result.append({
            "asin":         asin,
            "product_name": item.get("product_name") or item.get("name") or None,
            "date":         report_date,
            "revenue_usd":  float(item.get("total_sales") or item.get("revenue") or item.get("earnings") or 0),
            "orders":       int(item.get("total_purchases") or item.get("orders") or 0),
            "units_sold":   int(item.get("total_units_sold") or item.get("units") or 0),
        })
    return result

"""
Google Ads CSV report parser.

Google Ads exports start with a few metadata rows before the actual header.
Numbers may contain commas ("1,234"), percentages ("5.23%"), dashes ("--"),
or currency symbols ("$1.23"). This parser handles all of those.

Expected columns (case-insensitive, flexible naming):
  Day / Date                  → date
  Campaign                    → campaign_name
  Campaign status / Status    → campaign_status
  Campaign type               → campaign_type
  Impr.  / Impressions        → impressions
  Clicks                      → clicks
  Cost                        → spend_usd
  CTR                         → ctr
  Avg. CPC                    → avg_cpc
  Conv. rate                  → conv_rate
  Conversions                 → conversions
  Cost / conv.                → cost_per_conv
  Bid strategy                → bid_strategy
  Bid strategy type           → bid_strategy_type
  Budget                      → budget
  Budget type                 → budget_type
  Currency code               → currency_code
"""
import csv
import hashlib
import io
import logging
from datetime import date
from typing import Optional

from ..utils.asin_extractor import extract_asin

logger = logging.getLogger(__name__)

# Map of our canonical field names → list of CSV column name variants to try
_COLUMN_MAP: dict[str, list[str]] = {
    "date":            ["day", "date", "report date", "segment date"],
    "campaign_id":     ["campaign id", "campaign_id"],
    "campaign_name":   ["campaign", "campaign name"],
    "campaign_status": ["campaign status", "status"],
    "campaign_type":   ["campaign type"],
    "impressions":     ["impr.", "impressions", "impr"],
    "clicks":          ["clicks"],
    "spend_usd":       ["cost", "spend", "amount spent", "cost (usd)"],
    "ctr":             ["ctr"],
    "avg_cpc":         ["avg. cpc", "avg cpc", "average cpc"],
    "conv_rate":       ["conv. rate", "conv rate", "conversion rate"],
    "conversions":     ["conversions", "all conv.", "all conversions"],
    "cost_per_conv":   ["cost / conv.", "cost/conv", "cost per conversion", "cost / conversion"],
    "bid_strategy":    ["bid strategy", "bidding strategy"],
    "bid_strategy_type": ["bid strategy type", "bidding strategy type"],
    "budget":          ["budget"],
    "budget_type":     ["budget type"],
    "currency_code":   ["currency code", "currency"],
}


def _clean_number(value: str) -> Optional[float]:
    """Convert '1,234.56', '$1.23', '5.23%', '--' etc. to float or None."""
    if not value:
        return None
    v = value.strip().replace(",", "").replace("$", "").replace("%", "").replace("--", "")
    if not v or v == "-":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _clean_pct(value: str) -> Optional[float]:
    """Convert '5.23%' → 0.0523, or '5.23' → 0.0523."""
    n = _clean_number(value)
    if n is None:
        return None
    # If the raw value contains '%' it's already a percentage, divide by 100
    if "%" in value:
        return n / 100.0
    # Values < 1 are already decimal fractions
    if n <= 1.0:
        return n
    # Values > 1 assume they're percentages (e.g. Google exports CTR as "5.23" meaning 5.23%)
    return n / 100.0


def _make_campaign_id(campaign_name: str) -> str:
    """Stable ID from campaign name (since CSV has no numeric ID)."""
    return hashlib.md5(campaign_name.strip().lower().encode()).hexdigest()[:16]


def _build_col_index(headers: list[str]) -> dict[str, int]:
    """Build lowercase→index mapping from header row, normalizing all whitespace."""
    return {" ".join(h.split()).lower(): i for i, h in enumerate(headers)}


def _resolve(col_index: dict[str, int], candidates: list[str]) -> Optional[int]:
    """Find the first matching column index from a list of candidate names."""
    for name in candidates:
        if name in col_index:
            return col_index[name]
    return None


def _find_header_row(rows: list[list[str]]) -> Optional[int]:
    """
    Google Ads CSVs start with metadata rows. Find the row that contains
    'Campaign' or 'campaign' (the actual column header row).
    """
    for i, row in enumerate(rows):
        normalized = [" ".join(c.split()).lower() for c in row]
        if "campaign" in normalized:
            return i
    return None


def parse_google_ads_csv(content: bytes) -> list[dict]:
    """
    Parse a Google Ads CSV report. Returns a list of dicts ready for DB upsert.
    Raises ValueError with a descriptive message on bad input.
    """
    text = content.decode("utf-8-sig", errors="replace")  # handle BOM
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise ValueError("CSV file is empty.")

    header_row_idx = _find_header_row(rows)
    if header_row_idx is None:
        raise ValueError(
            "Could not find a header row containing 'Campaign'. "
            "Make sure you're uploading a Google Ads campaign report."
        )

    headers = rows[header_row_idx]
    col_index = _build_col_index(headers)

    # Resolve each canonical field to a column index
    field_cols: dict[str, Optional[int]] = {
        field: _resolve(col_index, candidates)
        for field, candidates in _COLUMN_MAP.items()
    }

    if field_cols["campaign_name"] is None:
        raise ValueError("Required column 'Campaign' not found in CSV.")
    if field_cols["date"] is None:
        raise ValueError(
            "Required date column not found. "
            "When exporting from Google Ads, add the 'Day' segment to include dates per row."
        )
    if field_cols["spend_usd"] is None:
        raise ValueError("Required column 'Cost' not found in CSV.")

    records = []
    skipped = 0

    for row_num, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 2):
        # Skip empty rows and summary/total rows
        if not row or not any(c.strip() for c in row):
            continue
        if len(row) <= (field_cols["campaign_name"] or 0):
            continue

        def get(field: str) -> str:
            idx = field_cols.get(field)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        campaign_name = get("campaign_name")
        if not campaign_name or campaign_name.lower() in ("total", "campaign", "--"):
            skipped += 1
            continue

        raw_date = get("date")
        parsed_date: Optional[date] = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                from datetime import datetime
                parsed_date = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                continue
        if parsed_date is None:
            logger.warning("Row %d: could not parse date %r, skipping.", row_num, raw_date)
            skipped += 1
            continue

        records.append({
            "campaign_id":      get("campaign_id") or _make_campaign_id(campaign_name),
            "campaign_name":    campaign_name,
            "asin":             extract_asin(campaign_name),
            "date":             parsed_date,
            "spend_usd":        _clean_number(get("spend_usd")) or 0.0,
            "clicks":           int(_clean_number(get("clicks")) or 0),
            "impressions":      int(_clean_number(get("impressions")) or 0),
            "conversions":      _clean_number(get("conversions")),
            "conv_rate":        _clean_pct(get("conv_rate")),
            "avg_cpc":          _clean_number(get("avg_cpc")),
            "cost_per_conv":    _clean_number(get("cost_per_conv")),
            "ctr":              _clean_pct(get("ctr")),
            "campaign_type":    get("campaign_type") or None,
            "campaign_status":  get("campaign_status") or None,
            "bid_strategy":     get("bid_strategy") or None,
            "bid_strategy_type":get("bid_strategy_type") or None,
            "budget":           _clean_number(get("budget")),
            "budget_type":      get("budget_type") or None,
            "currency_code":    get("currency_code") or None,
        })

    if not records:
        raise ValueError(
            f"No valid data rows found (skipped {skipped} rows). "
            "Check that the report contains daily data with a 'Day' segment."
        )

    logger.info("CSV parsed: %d records, %d skipped rows.", len(records), skipped)
    return records

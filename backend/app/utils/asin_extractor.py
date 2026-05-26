import re
from typing import Optional, Tuple

# Matches ASIN optionally followed by " - COUNTRYCODE" at end of campaign name.
# Group 1 = ASIN, group 2 = country code (optional).
# Examples:
#   "VALI Caffeine - B074G3SYTT"        → ("B074G3SYTT", None)
#   "Brand - B074G3SYTT - UK"           → ("B074G3SYTT", "UK")
_ASIN_COUNTRY_PATTERN = re.compile(
    r"(?:\s*-\s*)(B0[A-Z0-9]{8}|[0-9][A-Z0-9]{9})"
    r"(?:\s*-\s*([A-Z]{2}))?",
    re.IGNORECASE,
)

# Matches [Brand] or [Amazon] tag anywhere in the campaign name.
_CAMPAIGN_TYPE_PATTERN = re.compile(r'\[(Brand|Amazon)\]', re.IGNORECASE)


def extract_asin_and_country(campaign_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (asin, country_code) extracted from a campaign name, or (None, None)."""
    if not campaign_name:
        return None, None
    for m in _ASIN_COUNTRY_PATTERN.finditer(campaign_name):
        asin = m.group(1).upper()
        country = m.group(2).upper() if m.group(2) else None
        return asin, country
    return None, None


def extract_asin(campaign_name: str) -> Optional[str]:
    """Extract Amazon ASIN from a campaign name (backwards-compatible)."""
    asin, _ = extract_asin_and_country(campaign_name)
    return asin


def extract_campaign_type(campaign_name: str) -> Optional[str]:
    """
    Return 'brand' or 'amazon' if the campaign name contains [Brand] or [Amazon].
    Returns None for legacy campaigns without a type tag.
    Examples:
      "Product - [Brand] B0FZC2FVKW"  → "brand"
      "Product - [Amazon] B0FZC2FVKW" → "amazon"
      "Product - B0FZC2FVKW"          → None
    """
    if not campaign_name:
        return None
    m = _CAMPAIGN_TYPE_PATTERN.search(campaign_name)
    if m:
        return m.group(1).lower()  # "brand" or "amazon"
    return None

import re
from typing import Optional

# Matches Amazon ASIN at end of campaign name, after " - " separator.
# Handles hyphens inside brand names (e.g. "L-Theanine Plus - B074G3SYTT").
_ASIN_PATTERN = re.compile(
    r"(?:\s*-\s*)(B0[A-Z0-9]{8}|[0-9][A-Z0-9]{9})\s*$",
    re.IGNORECASE,
)


def extract_asin(campaign_name: str) -> Optional[str]:
    """
    Extract Amazon ASIN from a campaign name using the 'Brand - ASIN' pattern.

    Examples:
        "VALI Caffeine L-Theanine - B074G3SYTT" → "B074G3SYTT"
        "L-Theanine Plus - B074G3SYTT"          → "B074G3SYTT"
        "Brand Only Campaign"                    → None
    """
    if not campaign_name:
        return None
    m = _ASIN_PATTERN.search(campaign_name)
    if m:
        return m.group(1).upper()
    return None

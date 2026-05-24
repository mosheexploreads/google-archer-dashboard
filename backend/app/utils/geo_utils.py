from typing import Optional

# Maps individual Amazon marketplace country codes to Archer reporting geo groups.
COUNTRY_TO_GEO: dict[str, str] = {
    "US": "US",
    "UK": "EU", "GB": "EU", "DE": "EU", "FR": "EU",
    "IT": "EU", "ES": "EU", "NL": "EU", "PL": "EU", "SE": "EU",
    "JP": "FE", "AU": "FE", "SG": "FE", "IN": "FE",
    "CA": "CA",
}

# All known Archer reporting geos (used when looping sync).
ARCHER_GEOS = ["US", "EU", "FE", "CA"]


def country_to_geo(country_code: Optional[str]) -> str:
    """Return the Archer geo group for a country code, defaulting to 'US'."""
    if not country_code:
        return "US"
    return COUNTRY_TO_GEO.get(country_code.upper(), "US")

"""
Google Ads Editor CSV builder.

Takes a list of CampaignJobItem ORM objects (status='done') and returns a
4-file ZIP ready for import into Google Ads Editor.
"""
import csv
import io
import json
import zipfile
from typing import Any, Dict, List


def build_zip(items: List[Any]) -> bytes:
    """
    Build a Google Ads Editor ZIP (4 CSVs) from completed CampaignJobItem rows.
    Items without ad_copy or attribution_link are skipped silently.
    Returns ZIP bytes.
    """
    campaigns: List[Dict] = []
    ad_groups: List[Dict] = []
    keywords: List[Dict] = []
    ads: List[Dict] = []

    for item in items:
        if item.status != "done":
            continue
        if not item.attribution_link or not item.ad_copy:
            continue

        try:
            ad_data = json.loads(item.ad_copy)
        except (json.JSONDecodeError, TypeError):
            continue

        campaign_name = ad_data.get("campaign_name") or f"Amazon - {item.asin}"
        final_url = item.attribution_link

        # ── Campaign row ─────────────────────────────────────────────────────
        campaigns.append({
            "Campaign": campaign_name,
            "Campaign Type": "Search",
            "Networks": "Google Search",
            "Budget": "20",
            "Budget type": "Daily",
            "Campaign bidding strategy": "Maximize conversions",
            "Status": "Paused",
            "EU political ads": "No",
        })

        # ── Ad group row ─────────────────────────────────────────────────────
        ad_groups.append({
            "Campaign": campaign_name,
            "Ad Group": "Ad Group 1",
            "Status": "Enabled",
        })

        # ── Keyword rows ─────────────────────────────────────────────────────
        for kw in ad_data.get("keywords", []):
            if kw.startswith('"') and kw.endswith('"'):
                match_type = "Exact"
                kw_text = kw.strip('"')
            elif kw.startswith("[") and kw.endswith("]"):
                match_type = "Phrase"
                kw_text = kw.strip("[]")
            else:
                match_type = "Phrase"
                kw_text = kw

            keywords.append({
                "Campaign": campaign_name,
                "Ad Group": "Ad Group 1",
                "Keyword": kw_text,
                "Match Type": match_type,
                "Status": "Enabled",
            })

        # ── Ad row ───────────────────────────────────────────────────────────
        headlines = ad_data.get("headlines", [])
        descriptions = ad_data.get("descriptions", [])

        if headlines:
            ad_row: Dict = {
                "Campaign": campaign_name,
                "Ad Group": "Ad Group 1",
                "Ad Type": "Responsive search ad",
                "Final URL": final_url,
                "Status": "Enabled",
            }
            for i, h in enumerate(headlines[:15], 1):
                ad_row[f"Headline {i}"] = h[:30]
            for i, d in enumerate(descriptions[:4], 1):
                ad_row[f"Description {i}"] = d[:90]
            ads.append(ad_row)

    # ── Assemble ZIP ─────────────────────────────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("google_ads_campaigns.csv", _to_csv(campaigns))
        zf.writestr("google_ads_ad_groups.csv", _to_csv(ad_groups))
        zf.writestr("google_ads_keywords.csv", _to_csv(keywords))
        zf.writestr("google_ads_ads.csv", _to_csv(ads))

    return buf.getvalue()


def _clean_campaign_name(product_name: str, asin: str, tag: str) -> str:
    """Build 'Product Name - [Tag] ASIN', word-boundary truncated to keep it tidy."""
    pn = " ".join((product_name or "").split()).strip()
    if len(pn) > 50:
        cut = pn[:50].rsplit(" ", 1)[0].strip()
        pn = cut or pn[:50].strip()
    if not pn:
        pn = "Campaign"
    return f"{pn} - {tag} {asin}"


def build_zip_renamed(items: List[Any]) -> bytes:
    """
    Full 4-file Google Ads Editor ZIP for the given items, but with campaign names
    rebuilt from the product name ('Product Name - [Brand] ASIN') instead of the
    stored fallback ('Campaign - [Brand] ASIN'). Use to delete + re-import the
    empty, badly-named campaigns with correct names + keywords + ads in one go.
    """
    renamed: List[Any] = []
    for item in items:
        if item.status != "done" or not item.attribution_link or not item.ad_copy:
            continue
        try:
            ad = json.loads(item.ad_copy)
        except (json.JSONDecodeError, TypeError):
            continue
        if not (ad.get("headlines")):
            continue
        old = ad.get("campaign_name") or ""
        tag = "[Amazon]" if "[Amazon]" in old else "[Brand]"
        ad["campaign_name"] = _clean_campaign_name(item.product_name, item.asin, tag)
        # shallow proxy carrying the rewritten ad_copy + originals build_zip needs
        renamed.append(_ItemProxy(item, json.dumps(ad)))
    return build_zip(renamed)


class _ItemProxy:
    """Wraps a CampaignJobItem, overriding ad_copy with a rewritten campaign name."""
    def __init__(self, item: Any, ad_copy: str):
        self._item = item
        self.ad_copy = ad_copy
    def __getattr__(self, name):
        return getattr(self._item, name)


def build_delta_zip(items: List[Any]) -> bytes:
    """
    Build a 2-file ZIP (keywords + ads only) for items whose campaigns/ad-groups
    are ALREADY uploaded to Google Ads. Reuses each item's existing campaign_name
    so the rows attach to the existing campaigns. Enforces RSA minimums
    (>=3 unique headlines, >=2 descriptions) and dedupes headlines to avoid
    Google Ads Editor upload errors.
    """
    keywords: List[Dict] = []
    ads: List[Dict] = []

    for item in items:
        if item.status != "done" or not item.attribution_link or not item.ad_copy:
            continue
        try:
            ad_data = json.loads(item.ad_copy)
        except (json.JSONDecodeError, TypeError):
            continue

        headlines_raw = ad_data.get("headlines") or []
        if not headlines_raw:
            continue  # still empty — skip

        campaign_name = ad_data.get("campaign_name") or f"Campaign - [Brand] {item.asin}"

        for kw in ad_data.get("keywords", []):
            if kw.startswith('"') and kw.endswith('"'):
                match_type, kw_text = "Exact", kw.strip('"')
            elif kw.startswith("[") and kw.endswith("]"):
                match_type, kw_text = "Phrase", kw.strip("[]")
            else:
                match_type, kw_text = "Phrase", kw
            keywords.append({
                "Campaign": campaign_name, "Ad Group": "Ad Group 1",
                "Keyword": kw_text, "Match Type": match_type, "Status": "Enabled",
            })

        # dedupe headlines (case-insensitive), truncate to 30 chars
        seen_h = set()
        headlines: List[str] = []
        for h in headlines_raw:
            h = h[:30].strip()
            key = h.lower()
            if h and key not in seen_h:
                seen_h.add(key)
                headlines.append(h)
        descriptions = [d[:90].strip() for d in (ad_data.get("descriptions") or []) if d.strip()][:4]

        if len(headlines) < 3 or len(descriptions) < 2:
            continue  # would be rejected by Google as an incomplete RSA

        ad_row: Dict = {
            "Campaign": campaign_name, "Ad Group": "Ad Group 1",
            "Ad Type": "Responsive search ad", "Final URL": item.attribution_link,
            "Status": "Enabled",
        }
        for i, h in enumerate(headlines[:15], 1):
            ad_row[f"Headline {i}"] = h
        for i, dsc in enumerate(descriptions, 1):
            ad_row[f"Description {i}"] = dsc
        ads.append(ad_row)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("google_ads_keywords.csv", _to_csv(keywords))
        zf.writestr("google_ads_ads.csv", _to_csv(ads))
    return buf.getvalue()


def _to_csv(rows: List[Dict]) -> str:
    """Serialize a list of dicts to CSV, preserving insertion-order column set."""
    if not rows:
        return ""
    # Collect all keys in order of first appearance
    all_keys: List[str] = []
    seen = set()
    for row in rows:
        for k in row:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

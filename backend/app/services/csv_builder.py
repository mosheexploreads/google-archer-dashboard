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

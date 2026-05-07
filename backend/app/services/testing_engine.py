"""
Testing framework logic.

Rules (data-driven from 4,626-campaign historical analysis, Feb–May 2026):

  Stage 1 — cut if no sale within:
    AOV < $10  → 30 clicks
    AOV $10–20 → 60 clicks
    AOV > $20  → 100 clicks

  Stage 2 — at 100 clicks, if had ≥1 sale:
    RPC < CPC  → cut
    RPC ≥ CPC  → confirmed winner

  Bidding:
    Testing:  $0.50 flat (set at campaign launch, not changed here)
    Scaling:  RPC × 0.70  (100–199 clicks, confirmed winner)
    Mature:   RPC × 0.85  (200+ clicks, still profitable)
"""
import csv
import io
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from ..models import TestBatch, TestCampaign, GoogleAdsCampaignDay, ArcherProductDay
from ..schemas import TestCampaignStatus

logger = logging.getLogger(__name__)


def _cut_threshold(aov: float) -> int:
    if aov < 10:
        return 30
    if aov < 20:
        return 60
    return 100


def _compute_recommendation(
    tc: TestCampaign,
    clicks: int,
    orders: int,
    spend: float,
    revenue: float,
) -> Tuple[str, str, Optional[float]]:
    """Pure rule evaluation (ignoring applied/paused state). Returns (action, reason, new_bid)."""
    if clicks == 0:
        return "no_data", "No clicks recorded yet", None

    rpc = revenue / clicks
    cpc = spend / clicks

    # Stage 1: no sale at AOV-tier threshold
    if orders == 0 and clicks >= tc.cut_threshold:
        return (
            "cut",
            f"No orders at {clicks} clicks (threshold {tc.cut_threshold})",
            None,
        )

    # Stage 2: at 100 clicks, compare RPC vs CPC
    if clicks >= 100 and orders > 0:
        if rpc < cpc:
            return "cut", f"RPC ${rpc:.3f} < CPC ${cpc:.3f} at {clicks} clicks", None
        if clicks >= 200:
            bid = round(rpc * 0.85, 2)
            return "mature_bid", f"Mature winner: RPC ${rpc:.3f} × 0.85 = ${bid:.2f}", bid
        bid = round(rpc * 0.70, 2)
        return "scale_bid", f"Confirmed winner: RPC ${rpc:.3f} × 0.70 = ${bid:.2f}", bid

    return "testing", f"{clicks} clicks, {orders} orders — still testing", None


def _decide(
    tc: TestCampaign,
    clicks: int,
    orders: int,
    spend: float,
    revenue: float,
    campaign_status: Optional[str],
) -> Tuple[str, str, Optional[float]]:
    """
    Apply business rules including already-applied state.

    Returns "completed" if the campaign has already been actioned (paused in
    Google Ads, or the user marked the recommendation as applied), so the same
    recommendation isn't shown again.
    """
    # Auto-detected: already paused in Google Ads
    if campaign_status and campaign_status.lower() != "enabled":
        return "completed", f"Campaign {campaign_status.lower()} — testing complete", None

    rec_action, rec_reason, rec_bid = _compute_recommendation(
        tc, clicks, orders, spend, revenue
    )

    # User already marked the same recommendation as applied
    if (
        tc.last_applied_action
        and tc.last_applied_action == rec_action
        and rec_action in ("cut", "scale_bid", "mature_bid")
    ):
        when = (
            tc.last_applied_at.strftime("%Y-%m-%d")
            if tc.last_applied_at
            else "earlier"
        )
        return "completed", f"'{rec_action}' applied {when}", None

    return rec_action, rec_reason, rec_bid


def _latest_status_map(db: Session, campaign_names: List[str]) -> Dict[str, Optional[str]]:
    """For each campaign_name, return the campaign_status from the most recent date."""
    if not campaign_names:
        return {}
    rows = (
        db.query(
            GoogleAdsCampaignDay.campaign_name,
            GoogleAdsCampaignDay.campaign_status,
            GoogleAdsCampaignDay.date,
        )
        .filter(GoogleAdsCampaignDay.campaign_name.in_(campaign_names))
        .order_by(GoogleAdsCampaignDay.campaign_name, desc(GoogleAdsCampaignDay.date))
        .all()
    )
    out: Dict[str, Optional[str]] = {}
    for name, status, _date in rows:
        if name not in out:  # first row wins (latest date due to desc sort)
            out[name] = status
    return out


def evaluate_campaigns(db: Session) -> List[TestCampaignStatus]:
    """Evaluate all test campaigns against current GoogleAdsCampaignDay / ArcherProductDay data."""
    campaigns = db.query(TestCampaign).all()
    batches = {b.id: b for b in db.query(TestBatch).all()}
    status_map = _latest_status_map(db, [tc.campaign_name for tc in campaigns])

    results = []
    for tc in campaigns:
        # Lifetime clicks + spend by campaign name
        ads_row = (
            db.query(
                func.coalesce(func.sum(GoogleAdsCampaignDay.clicks), 0).label("clicks"),
                func.coalesce(func.sum(GoogleAdsCampaignDay.spend_usd), 0.0).label("spend"),
            )
            .filter(GoogleAdsCampaignDay.campaign_name == tc.campaign_name)
            .one()
        )

        # Lifetime orders + revenue from Archer by ASIN
        orders = 0
        revenue = 0.0
        if tc.asin:
            arch_row = (
                db.query(
                    func.coalesce(func.sum(ArcherProductDay.orders), 0).label("orders"),
                    func.coalesce(func.sum(ArcherProductDay.revenue_usd), 0.0).label("revenue"),
                )
                .filter(ArcherProductDay.asin == tc.asin)
                .one()
            )
            orders = int(arch_row.orders)
            revenue = float(arch_row.revenue)

        clicks = int(ads_row.clicks)
        spend = float(ads_row.spend)

        action, reason, new_bid = _decide(
            tc, clicks, orders, spend, revenue,
            campaign_status=status_map.get(tc.campaign_name),
        )

        rpc = round(revenue / clicks, 3) if clicks > 0 else None
        cpc = round(spend / clicks, 3) if clicks > 0 else None

        batch_name = batches[tc.batch_id].name if tc.batch_id in batches else ""

        results.append(
            TestCampaignStatus(
                id=tc.id,
                batch_id=tc.batch_id,
                batch_name=batch_name,
                campaign_name=tc.campaign_name,
                asin=tc.asin,
                expected_aov=tc.expected_aov,
                cut_threshold=tc.cut_threshold,
                clicks=clicks,
                orders=orders,
                spend_usd=round(spend, 2),
                revenue_usd=round(revenue, 2),
                rpc=rpc,
                cpc=cpc,
                action=action,
                new_bid=new_bid,
                action_reason=reason,
            )
        )

    return results


def parse_batch_csv(content: bytes) -> List[dict]:
    """
    Parse batch CSV.

    Required columns (case-insensitive, spaces→underscores):
      campaign_name, price, commission_rate
    Optional:
      asin
    """
    text = content.decode("utf-8-sig").strip()
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")

    norm = {h: h.strip().lower().replace(" ", "_") for h in reader.fieldnames}
    required = {"campaign_name", "price", "commission_rate"}
    missing = required - set(norm.values())
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}. "
            f"Found: {sorted(norm.values())}"
        )

    records = []
    for i, raw in enumerate(reader, start=2):
        row = {norm[k]: (v or "").strip() for k, v in raw.items() if k in norm}
        try:
            price = float(row["price"])
            rate = float(row["commission_rate"])
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Row {i}: invalid price/commission_rate — {exc}") from exc
        if price <= 0 or rate <= 0:
            raise ValueError(f"Row {i}: price and commission_rate must be positive numbers")
        records.append(
            {
                "campaign_name": row["campaign_name"],
                "asin": row.get("asin", "") or None,
                "price": price,
                "commission_rate": rate,
            }
        )

    if not records:
        raise ValueError("CSV has no data rows")
    return records


def build_google_ads_export(campaigns: List[TestCampaignStatus]) -> str:
    """
    Build Google Ads Editor bulk CSV.

    Only action rows are included (cut or bid change).
    Google Ads Editor format: fill Campaign + one of Status or CPC cap, never both.
    """
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["Campaign", "Campaign Status", "Campaign bid strategy max. CPC bid limit"]
    )

    for c in campaigns:
        if c.action == "cut":
            writer.writerow([c.campaign_name, "Paused", ""])
        elif c.action in ("scale_bid", "mature_bid") and c.new_bid is not None:
            writer.writerow([c.campaign_name, "", f"{c.new_bid:.2f}"])

    return out.getvalue()

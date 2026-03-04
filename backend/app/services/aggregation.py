"""
Aggregation queries: JOIN Google Ads + Archer by ASIN + date.
Two query patterns:
  1. get_campaigns  — campaign-level aggregates (no date dimension)
  2. get_campaign_dates — per-period rows for one campaign

Revenue de-duplication: when multiple campaigns share the same ASIN on the
same day, Archer revenue/orders are divided equally across those campaigns so
totals never double-count.
"""
from datetime import date
from typing import Optional, List, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..schemas import SummaryResponse, CampaignRow, DateRow, TimeseriesPoint

GroupBy = Literal["day", "week", "month"]


def _safe_float(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _period_expr(groupby: str) -> str:
    """Return SQLite expression to group dates into day/week/month periods."""
    if groupby == "week":
        # ISO week: 2026-W07
        return "strftime('%Y-W%W', g.date)"
    if groupby == "month":
        return "strftime('%Y-%m', g.date)"
    return "g.date"  # day (default)


# Subquery: count how many campaigns share the same (asin, date) in the range.
# Used to pro-rate Archer revenue so it is never double-counted.
_CC_SUBQUERY = (
    " LEFT JOIN ("
    "   SELECT asin, date, COUNT(*) AS cnt"
    "   FROM google_ads_campaign_day"
    "   WHERE date BETWEEN :date_from AND :date_to AND asin IS NOT NULL"
    "   GROUP BY asin, date"
    " ) cc ON g.asin = cc.asin AND g.date = cc.date"
)

_SORT_WHITELIST = {
    "campaign_name", "asin", "spend_usd", "revenue_usd",
    "roas", "rpc", "acos", "orders", "units_sold",
    "clicks", "impressions", "ctr", "cpc", "profit", "conv_rate",
}

# ── Summary ──────────────────────────────────────────────────────────────────

def get_summary(db: Session, date_from: date, date_to: date) -> SummaryResponse:
    sql = text(
        "SELECT"
        "  COALESCE(SUM(g.spend_usd), 0)                                  AS spend_usd,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)          AS revenue_usd,"
        "  COALESCE(SUM(g.clicks), 0)                                     AS clicks,"
        "  COALESCE(SUM(g.impressions), 0)                                AS impressions,"
        "  COALESCE(SUM(a.orders      / COALESCE(cc.cnt, 1)), 0)          AS orders,"
        "  COALESCE(SUM(a.units_sold  / COALESCE(cc.cnt, 1)), 0)          AS units_sold"
        " FROM google_ads_campaign_day g"
        " LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date"
        + _CC_SUBQUERY +
        " WHERE g.date BETWEEN :date_from AND :date_to"
    )
    row = db.execute(sql, {"date_from": date_from, "date_to": date_to}).fetchone()
    spend = float(row.spend_usd)
    revenue = float(row.revenue_usd)
    clicks = int(row.clicks)
    return SummaryResponse(
        spend_usd=spend,
        revenue_usd=revenue,
        roas=revenue / spend if spend > 0 else None,
        rpc=revenue / clicks if clicks > 0 else None,
        acos=spend / revenue if revenue > 0 else None,
        orders=int(row.orders),
        units_sold=int(row.units_sold),
        clicks=clicks,
        impressions=int(row.impressions),
        date_from=str(date_from),
        date_to=str(date_to),
    )


# ── Campaign-level aggregates (no date dimension) ────────────────────────────

def get_campaigns(
    db: Session,
    date_from: date,
    date_to: date,
    sort_by: str = "spend_usd",
    sort_dir: str = "desc",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
) -> List[CampaignRow]:
    if sort_by not in _SORT_WHITELIST:
        sort_by = "spend_usd"
    dir_sql = "DESC" if sort_dir.lower() == "desc" else "ASC"

    sql = text(
        "SELECT"
        "  g.campaign_id,"
        "  g.campaign_name,"
        "  g.asin,"
        "  MAX(a.product_name)                                                  AS product_name,"
        "  SUM(g.impressions)                                                   AS impressions,"
        "  SUM(g.clicks)                                                        AS clicks,"
        "  SUM(g.spend_usd)                                                     AS spend_usd,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)               AS revenue_usd,"
        "  COALESCE(SUM(a.orders      / COALESCE(cc.cnt, 1)), 0)               AS orders,"
        "  COALESCE(SUM(a.units_sold  / COALESCE(cc.cnt, 1)), 0)               AS units_sold,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)         END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                          END AS cpc,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "            / SUM(g.clicks)                                            END AS rpc,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN CAST(COALESCE(SUM(a.orders / COALESCE(cc.cnt, 1)), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                            END AS conv_rate,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "    - SUM(g.spend_usd)                                                 AS profit,"
        "  CASE WHEN SUM(g.spend_usd) > 0"
        "       THEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "            / SUM(g.spend_usd)                                         END AS roas,"
        "  CASE WHEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0) > 0"
        "       THEN SUM(g.spend_usd)"
        "            / COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)   END AS acos,"
        "  ls.campaign_status                                                   AS current_status"
        " FROM google_ads_campaign_day g"
        " LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date"
        + _CC_SUBQUERY +
        " LEFT JOIN ("
        "   SELECT g2.campaign_id, g2.campaign_status"
        "   FROM google_ads_campaign_day g2"
        "   INNER JOIN ("
        "     SELECT campaign_id, MAX(date) AS max_date"
        "     FROM google_ads_campaign_day"
        "     WHERE campaign_status IS NOT NULL"
        "     GROUP BY campaign_id"
        "   ) ld ON g2.campaign_id = ld.campaign_id AND g2.date = ld.max_date"
        "   GROUP BY g2.campaign_id"
        " ) ls ON g.campaign_id = ls.campaign_id"
        " WHERE g.date BETWEEN :date_from AND :date_to"
        "   AND (:asin     = '' OR g.asin LIKE '%' || :asin || '%')"
        "   AND (:campaign = '' OR g.campaign_name LIKE '%' || :campaign || '%')"
        "   AND (:status   = '' OR COALESCE(ls.campaign_status, '') = :status)"
        " GROUP BY g.campaign_id, g.asin"
        f" ORDER BY {sort_by} {dir_sql}"
    )

    rows = db.execute(sql, {
        "date_from": date_from,
        "date_to": date_to,
        "asin": asin_filter,
        "campaign": campaign_filter,
        "status": status_filter,
    }).fetchall()

    return [
        CampaignRow(
            campaign_id=r.campaign_id,
            campaign_name=r.campaign_name,
            asin=r.asin,
            product_name=r.product_name,
            impressions=int(r.impressions or 0),
            clicks=int(r.clicks or 0),
            ctr=_safe_float(r.ctr),
            spend_usd=float(r.spend_usd or 0),
            cpc=_safe_float(r.cpc),
            orders=int(r.orders or 0),
            conv_rate=_safe_float(r.conv_rate),
            revenue_usd=float(r.revenue_usd or 0),
            rpc=_safe_float(r.rpc),
            profit=float(r.profit or 0),
            roas=_safe_float(r.roas),
            acos=_safe_float(r.acos),
            units_sold=int(r.units_sold or 0),
            current_status=r.current_status,
        )
        for r in rows
    ]


# ── Date drill-down (per campaign, per period) ───────────────────────────────

def get_campaign_dates(
    db: Session,
    campaign_id: str,
    date_from: date,
    date_to: date,
    groupby: str = "day",
) -> List[DateRow]:
    period_expr = _period_expr(groupby)

    sql = text(
        f"SELECT"
        f"  {period_expr}                                                        AS period,"
        "  SUM(g.impressions)                                                   AS impressions,"
        "  SUM(g.clicks)                                                        AS clicks,"
        "  SUM(g.spend_usd)                                                     AS spend_usd,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)               AS revenue_usd,"
        "  COALESCE(SUM(a.orders      / COALESCE(cc.cnt, 1)), 0)               AS orders,"
        "  COALESCE(SUM(a.units_sold  / COALESCE(cc.cnt, 1)), 0)               AS units_sold,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)         END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                          END AS cpc,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "            / SUM(g.clicks)                                            END AS rpc,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN CAST(COALESCE(SUM(a.orders / COALESCE(cc.cnt, 1)), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                            END AS conv_rate,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "    - SUM(g.spend_usd)                                                 AS profit,"
        "  CASE WHEN SUM(g.spend_usd) > 0"
        "       THEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "            / SUM(g.spend_usd)                                         END AS roas,"
        "  CASE WHEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0) > 0"
        "       THEN SUM(g.spend_usd)"
        "            / COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)   END AS acos"
        " FROM google_ads_campaign_day g"
        " LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date"
        + _CC_SUBQUERY +
        " WHERE g.campaign_id = :campaign_id"
        "   AND g.date BETWEEN :date_from AND :date_to"
        " GROUP BY period"
        " ORDER BY period ASC"
    )

    rows = db.execute(sql, {
        "campaign_id": campaign_id,
        "date_from": date_from,
        "date_to": date_to,
    }).fetchall()

    return [
        DateRow(
            period=str(r.period),
            impressions=int(r.impressions or 0),
            clicks=int(r.clicks or 0),
            ctr=_safe_float(r.ctr),
            spend_usd=float(r.spend_usd or 0),
            cpc=_safe_float(r.cpc),
            orders=int(r.orders or 0),
            conv_rate=_safe_float(r.conv_rate),
            revenue_usd=float(r.revenue_usd or 0),
            rpc=_safe_float(r.rpc),
            profit=float(r.profit or 0),
            roas=_safe_float(r.roas),
            acos=_safe_float(r.acos),
            units_sold=int(r.units_sold or 0),
        )
        for r in rows
    ]


# ── Timeseries ────────────────────────────────────────────────────────────────

def get_timeseries(
    db: Session,
    date_from: date,
    date_to: date,
    groupby: str = "day",
) -> List[TimeseriesPoint]:
    period_expr = _period_expr(groupby)

    sql = text(
        f"SELECT"
        f"  {period_expr}                                                        AS period,"
        "  SUM(g.impressions)                                                   AS impressions,"
        "  SUM(g.clicks)                                                        AS clicks,"
        "  SUM(g.spend_usd)                                                     AS spend_usd,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)               AS revenue_usd,"
        "  COALESCE(SUM(a.orders      / COALESCE(cc.cnt, 1)), 0)               AS orders,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)         END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                          END AS cpc,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "            / SUM(g.clicks)                                            END AS rpc,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN CAST(COALESCE(SUM(a.orders / COALESCE(cc.cnt, 1)), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                            END AS conv_rate,"
        "  COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "    - SUM(g.spend_usd)                                                 AS profit,"
        "  CASE WHEN SUM(g.spend_usd) > 0"
        "       THEN COALESCE(SUM(a.revenue_usd / COALESCE(cc.cnt, 1)), 0)"
        "            / SUM(g.spend_usd)                                         END AS roas"
        " FROM google_ads_campaign_day g"
        " LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date"
        + _CC_SUBQUERY +
        " WHERE g.date BETWEEN :date_from AND :date_to"
        " GROUP BY period"
        " ORDER BY period ASC"
    )

    rows = db.execute(sql, {"date_from": date_from, "date_to": date_to}).fetchall()

    return [
        TimeseriesPoint(
            period=str(r.period),
            impressions=int(r.impressions or 0),
            clicks=int(r.clicks or 0),
            ctr=_safe_float(r.ctr),
            spend_usd=float(r.spend_usd or 0),
            cpc=_safe_float(r.cpc),
            orders=int(r.orders or 0),
            conv_rate=_safe_float(r.conv_rate),
            revenue_usd=float(r.revenue_usd or 0),
            rpc=_safe_float(r.rpc),
            profit=float(r.profit or 0),
            roas=_safe_float(r.roas),
        )
        for r in rows
    ]

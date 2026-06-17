"""
Aggregation queries: JOIN Google Ads + Archer by ASIN + date.
Two query patterns:
  1. get_campaigns  — campaign-level aggregates (no date dimension)
  2. get_campaign_dates — per-period rows for one campaign

Revenue de-duplication (two-level fallback):
  1. If ≥1 campaign for an ASIN+date has spend > 0, only those campaigns share the
     Archer revenue; paused ($0-spend) siblings receive $0 so totals don't inflate.
  2. If ALL campaigns for that ASIN+date have $0 spend (all paused), every campaign
     receives an equal share so revenue is never silently dropped.
"""
from datetime import date
from typing import Optional, List, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..schemas import (
    SummaryResponse, CampaignRow, DateRow, TimeseriesPoint, ProductWarning, DetailedExportRow,
    CampaignProductRow, CampaignProductsResponse, HaloOpportunityRow, HaloOpportunitiesResponse,
)
from ..utils.geo_utils import country_to_geo
from ..config import get_settings
from . import cache

# Allowed values for the revenue_source param; anything else falls back to "auto".
_REVENUE_SOURCES = {"auto", "legacy", "new"}


def _norm_source(revenue_source: str) -> str:
    return revenue_source if revenue_source in _REVENUE_SOURCES else "auto"

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


# Subquery: per (asin, date, campaign_type) compute
#   cnt_active — campaigns with spend > 0
#   cnt        — effective denominator: cnt_active if any are active, else total count
#                (so revenue is never lost when all campaigns are paused)
#
# Partitioning by campaign_type (brand vs amazon) ensures that amazon campaign rows
# only share revenue from the amazon Archer link, not the brand link — preventing
# fake revenue from appearing on amazon campaigns when only the brand link earned money.
_CC_SUBQUERY = (
    " LEFT JOIN ("
    "   SELECT asin, date, COALESCE(campaign_type, 'brand') AS ctype,"
    "     SUM(CASE WHEN spend_usd > 0 THEN 1 ELSE 0 END) AS cnt_active,"
    "     CASE WHEN SUM(CASE WHEN spend_usd > 0 THEN 1 ELSE 0 END) > 0"
    "          THEN SUM(CASE WHEN spend_usd > 0 THEN 1 ELSE 0 END)"
    "          ELSE COUNT(*)"
    "     END AS cnt"
    "   FROM google_ads_campaign_day"
    "   WHERE date BETWEEN :date_from AND :date_to AND asin IS NOT NULL"
    "   GROUP BY asin, date, COALESCE(campaign_type, 'brand')"
    " ) cc ON g.asin = cc.asin AND g.date = cc.date"
    "   AND cc.ctype = COALESCE(g.campaign_type, 'brand')"
)


def _cc_share(col: str) -> str:
    """
    SQL expression for the Archer metric (revenue / orders / units_sold) share
    attributable to a single campaign row (alias g).

    A row earns its share when:
      - g.spend_usd > 0 (campaign was active that day), OR
      - cnt_active = 0 (ALL campaigns for this ASIN+date were paused — fall back
        equally so revenue is never silently dropped).

    Campaigns with spend = 0 that have at least one active sibling receive $0.
    """
    return (
        f"CASE WHEN g.spend_usd > 0 OR COALESCE(cc.cnt_active, 0) = 0"
        f" THEN {col} / COALESCE(cc.cnt, 1) ELSE 0 END"
    )

# When filtering by country_code, restrict the Archer JOIN to the matching geo.
# Without a filter join only US geo — all current campaigns are US campaigns and
# summing all geos would inflate revenue with EU/FE/CA data unrelated to the ad spend.
# link_type matches campaign_type so brand campaigns see brand-link revenue only,
# and amazon campaigns see amazon-link revenue only (which is $0 for most ASINs).
def _archer_join(country_code: str = "", revenue_source: str = "auto") -> str:
    link_cond = "AND a.link_type = COALESCE(g.campaign_type, 'brand')"

    # Source selection: both APIs' rows coexist in archer_product_day, keyed by
    # `source`. "auto" = legacy before the cutover (Archer's commission-model
    # change date), new from it onward. The cutover comes from server config —
    # interpolated like geo, never user input.
    src = _norm_source(revenue_source)
    if src == "auto":
        cutover = get_settings().archer_source_cutover
        source_cond = (
            f" AND ((a.date < '{cutover}' AND a.source = 'legacy')"
            f" OR (a.date >= '{cutover}' AND a.source = 'new'))"
        )
    else:
        source_cond = f" AND a.source = '{src}'"

    geo = country_to_geo(country_code) if country_code else "US"
    return (
        f" LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date"
        f" AND a.geo = '{geo}' {link_cond}{source_cond}"
    )


# ── Shared dashboard filters (campaign / asin / status / type / age / country) ─
# These let the summary, chart, and daily-breakdown table reflect the same
# campaign subset the campaign table filters client-side.

# Latest known status per campaign (status from its most recent dated row).
_LATEST_STATUS_JOIN = (
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
)

# First date a campaign was ever seen — used to compute age in days.
_FIRST_SEEN_JOIN = (
    " LEFT JOIN ("
    "   SELECT campaign_id, MIN(date) AS first_seen"
    "   FROM google_ads_campaign_day"
    "   GROUP BY campaign_id"
    " ) fs ON g.campaign_id = fs.campaign_id"
)


def _filter_clause(
    country_code: str = "",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
    campaign_type_filter: str = "",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    account_filter: str = "",
) -> tuple:
    """
    Build (extra_joins, where_fragment, params) for the active dashboard filters.

    Joins are only added when the filter that needs them is set: the latest-status
    and first-seen joins each do a full-table GROUP BY, so adding them
    unconditionally slows the common no-filter view. Mirrors the campaign table's
    client-side filter semantics so totals stay consistent across views.
    """
    joins = ""
    conds: list = []
    params: dict = {}

    if asin_filter:
        conds.append("g.asin LIKE '%' || :f_asin || '%'")
        params["f_asin"] = asin_filter
    if campaign_filter:
        conds.append("g.campaign_name LIKE '%' || :f_campaign || '%'")
        params["f_campaign"] = campaign_filter
    if campaign_type_filter:
        conds.append("COALESCE(g.campaign_type, 'brand') = :f_type")
        params["f_type"] = campaign_type_filter
    if account_filter:
        conds.append("g.account = :f_account")
        params["f_account"] = account_filter
    if country_code:
        # NULL country_code is treated as US, matching the campaign table.
        conds.append("(g.country_code = :f_country OR (:f_country = 'US' AND g.country_code IS NULL))")
        params["f_country"] = country_code
    if status_filter:
        joins += _LATEST_STATUS_JOIN
        conds.append("COALESCE(ls.campaign_status, '') = :f_status")
        params["f_status"] = status_filter
    if age_min is not None or age_max is not None:
        joins += _FIRST_SEEN_JOIN
        if age_min is not None:
            conds.append("CAST(julianday('now') - julianday(fs.first_seen) AS INTEGER) >= :f_age_min")
            params["f_age_min"] = age_min
        if age_max is not None:
            conds.append("CAST(julianday('now') - julianday(fs.first_seen) AS INTEGER) <= :f_age_max")
            params["f_age_max"] = age_max

    where = (" AND " + " AND ".join("(%s)" % c for c in conds)) if conds else ""
    return joins, where, params


# Map sort_by param to the qualified column expression used in ORDER BY.
# Unqualified names like "asin" are ambiguous when multiple JOINed tables
# have the same column, so we use the table alias explicitly.
_SORT_WHITELIST = {
    "campaign_name", "asin", "spend_usd", "revenue_usd",
    "roas", "rpc", "acos", "orders", "units_sold",
    "clicks", "impressions", "ctr", "cpc", "profit", "conv_rate",
}
_SORT_COL = {
    "asin":          "g.asin",
    "campaign_name": "g.campaign_name",
    "spend_usd":     "spend_usd",
    "revenue_usd":   "revenue_usd",
    "roas":          "roas",
    "rpc":           "rpc",
    "acos":          "acos",
    "orders":        "orders",
    "units_sold":    "units_sold",
    "clicks":        "clicks",
    "impressions":   "impressions",
    "ctr":           "ctr",
    "cpc":           "cpc",
    "profit":        "profit",
    "conv_rate":     "conv_rate",
}

# ── Summary ──────────────────────────────────────────────────────────────────

def get_summary(
    db: Session,
    date_from: date,
    date_to: date,
    country_code: str = "",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
    campaign_type_filter: str = "",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    account_filter: str = "",
    revenue_source: str = "auto",
) -> SummaryResponse:
    revenue_source = _norm_source(revenue_source)
    key = ("summary", date_from, date_to, country_code, asin_filter,
           campaign_filter, status_filter, campaign_type_filter, age_min, age_max,
           account_filter, revenue_source)
    return cache.get_or_compute(key, lambda: _summary_uncached(
        db, date_from, date_to, country_code, asin_filter, campaign_filter,
        status_filter, campaign_type_filter, age_min, age_max, account_filter,
        revenue_source,
    ))


def _summary_uncached(
    db: Session,
    date_from: date,
    date_to: date,
    country_code: str = "",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
    campaign_type_filter: str = "",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    account_filter: str = "",
    revenue_source: str = "auto",
) -> SummaryResponse:
    joins, where, fparams = _filter_clause(
        country_code, asin_filter, campaign_filter,
        status_filter, campaign_type_filter, age_min, age_max, account_filter,
    )
    sql = text(
        "SELECT"
        "  COALESCE(SUM(g.spend_usd), 0)                                  AS spend_usd,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)                AS revenue_usd,"
        f" COALESCE(SUM({_cc_share('a.total_sales_usd')}), 0)           AS total_sales_usd,"
        "  COALESCE(SUM(g.clicks), 0)                                     AS clicks,"
        "  COALESCE(SUM(g.impressions), 0)                                AS impressions,"
        f" COALESCE(SUM({_cc_share('a.orders')}), 0)                     AS orders,"
        f" COALESCE(SUM({_cc_share('a.units_sold')}), 0)                 AS units_sold"
        " FROM google_ads_campaign_day g"
        + _archer_join(country_code, revenue_source)
        + _CC_SUBQUERY
        + joins
        + " WHERE g.date BETWEEN :date_from AND :date_to"
        + where
    )
    params: dict = {"date_from": date_from, "date_to": date_to}
    params.update(fparams)
    row = db.execute(sql, params).fetchone()
    spend = float(row.spend_usd)
    revenue = float(row.revenue_usd)
    clicks = int(row.clicks)
    return SummaryResponse(
        spend_usd=spend,
        revenue_usd=revenue,
        total_sales_usd=float(row.total_sales_usd),
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
    country_code: str = "",
    campaign_type_filter: str = "",
    account_filter: str = "",
    revenue_source: str = "auto",
) -> List[CampaignRow]:
    revenue_source = _norm_source(revenue_source)
    key = ("campaigns", date_from, date_to, sort_by, sort_dir, asin_filter,
           campaign_filter, status_filter, country_code, campaign_type_filter,
           account_filter, revenue_source)
    return cache.get_or_compute(key, lambda: _campaigns_uncached(
        db, date_from, date_to, sort_by, sort_dir, asin_filter,
        campaign_filter, status_filter, country_code, campaign_type_filter,
        account_filter, revenue_source,
    ))


def _campaigns_uncached(
    db: Session,
    date_from: date,
    date_to: date,
    sort_by: str = "spend_usd",
    sort_dir: str = "desc",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
    country_code: str = "",
    campaign_type_filter: str = "",
    account_filter: str = "",
    revenue_source: str = "auto",
) -> List[CampaignRow]:
    if sort_by not in _SORT_WHITELIST:
        sort_by = "spend_usd"
    sort_col = _SORT_COL.get(sort_by, sort_by)
    dir_sql = "DESC" if sort_dir.lower() == "desc" else "ASC"

    country_filter = "AND g.country_code = :country_code" if country_code else ""
    sql = text(
        "SELECT"
        "  g.campaign_id,"
        "  COALESCE(ln.latest_name, g.campaign_name) AS campaign_name,"
        "  MAX(g.asin)                                                           AS asin,"
        "  COALESCE(MAX(g.country_code), 'US')                                  AS country_code,"
        "  MAX(g.account)                                                       AS account,"
        "  MAX(a.product_name)                                                  AS product_name,"
        "  SUM(g.impressions)                                                   AS impressions,"
        "  SUM(g.clicks)                                                        AS clicks,"
        "  SUM(g.spend_usd)                                                     AS spend_usd,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)                      AS revenue_usd,"
        f" COALESCE(SUM({_cc_share('a.total_sales_usd')}), 0)                 AS total_sales_usd,"
        f" COALESCE(SUM({_cc_share('a.orders')}), 0)                           AS orders,"
        f" COALESCE(SUM({_cc_share('a.units_sold')}), 0)                       AS units_sold,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)         END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                          END AS cpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.clicks)                                            END AS rpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN CAST(COALESCE(SUM({_cc_share('a.orders')}), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                            END AS conv_rate,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "    - SUM(g.spend_usd)                                                 AS profit,"
        f" CASE WHEN SUM(g.spend_usd) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.spend_usd)                                         END AS roas,"
        f" CASE WHEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0) > 0"
        "       THEN SUM(g.spend_usd)"
        f"           / COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)          END AS acos,"
        "  ls.campaign_status                                                   AS current_status,"
        "  fs.first_seen                                                        AS first_seen,"
        "  MAX(g.campaign_type)                                                 AS campaign_type"
        " FROM google_ads_campaign_day g"
        + _archer_join(country_code, revenue_source)
        + _CC_SUBQUERY
        + " LEFT JOIN ("
        "   SELECT campaign_id, MIN(date) AS first_seen"
        "   FROM google_ads_campaign_day"
        "   GROUP BY campaign_id"
        " ) fs ON g.campaign_id = fs.campaign_id"
        " LEFT JOIN ("
        "   SELECT g2.campaign_id, g2.campaign_status, MAX(g2.campaign_name) AS latest_name"
        "   FROM google_ads_campaign_day g2"
        "   INNER JOIN ("
        "     SELECT campaign_id, MAX(date) AS max_date"
        "     FROM google_ads_campaign_day"
        "     WHERE campaign_status IS NOT NULL"
        "     GROUP BY campaign_id"
        "   ) ld ON g2.campaign_id = ld.campaign_id AND g2.date = ld.max_date"
        "   GROUP BY g2.campaign_id"
        " ) ls ON g.campaign_id = ls.campaign_id"
        " LEFT JOIN ("
        "   SELECT g2.campaign_id, MAX(g2.campaign_name) AS latest_name"
        "   FROM google_ads_campaign_day g2"
        "   INNER JOIN ("
        "     SELECT campaign_id, MAX(date) AS max_date"
        "     FROM google_ads_campaign_day"
        "     GROUP BY campaign_id"
        "   ) ld2 ON g2.campaign_id = ld2.campaign_id AND g2.date = ld2.max_date"
        "   GROUP BY g2.campaign_id"
        " ) ln ON g.campaign_id = ln.campaign_id"
        " WHERE g.date BETWEEN :date_from AND :date_to"
        "   AND (:asin     = '' OR g.asin LIKE '%' || :asin || '%')"
        "   AND (:campaign = '' OR g.campaign_name LIKE '%' || :campaign || '%')"
        "   AND (:status   = '' OR COALESCE(ls.campaign_status, '') = :status)"
        "   AND (:campaign_type_filter = '' OR COALESCE(g.campaign_type, 'brand') = :campaign_type_filter)"
        "   AND (:account_filter = '' OR g.account = :account_filter)"
        f"  {country_filter}"
        " GROUP BY g.campaign_id"
        # Drop campaigns with no activity in the selected range — Google Ads
        # exports a row per campaign per day even when idle, which on this
        # account is ~90% of rows and bloated the payload to ~7 MB.
        " HAVING SUM(g.impressions) > 0 OR SUM(g.clicks) > 0"
        "     OR SUM(g.spend_usd) > 0"
        f"    OR COALESCE(SUM({_cc_share('a.revenue_usd')}), 0) > 0"
        f" ORDER BY {sort_col} {dir_sql}"
    )

    params: dict = {
        "date_from": date_from,
        "date_to": date_to,
        "asin": asin_filter,
        "campaign": campaign_filter,
        "status": status_filter,
        "campaign_type_filter": campaign_type_filter,
        "account_filter": account_filter,
    }
    if country_code:
        params["country_code"] = country_code
    rows = db.execute(sql, params).fetchall()

    return [
        CampaignRow(
            campaign_id=r.campaign_id,
            campaign_name=r.campaign_name,
            asin=r.asin,
            country_code=r.country_code,
            account=r.account,
            product_name=r.product_name,
            impressions=int(r.impressions or 0),
            clicks=int(r.clicks or 0),
            ctr=_safe_float(r.ctr),
            spend_usd=float(r.spend_usd or 0),
            cpc=_safe_float(r.cpc),
            orders=int(r.orders or 0),
            conv_rate=_safe_float(r.conv_rate),
            revenue_usd=float(r.revenue_usd or 0),
            total_sales_usd=float(r.total_sales_usd or 0),
            rpc=_safe_float(r.rpc),
            profit=float(r.profit or 0),
            roas=_safe_float(r.roas),
            acos=_safe_float(r.acos),
            units_sold=int(r.units_sold or 0),
            current_status=r.current_status,
            first_seen=str(r.first_seen) if r.first_seen else None,
            campaign_type=r.campaign_type,
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
    revenue_source: str = "auto",
) -> List[DateRow]:
    revenue_source = _norm_source(revenue_source)
    key = ("campaign_dates", campaign_id, date_from, date_to, groupby, revenue_source)
    return cache.get_or_compute(key, lambda: _campaign_dates_uncached(
        db, campaign_id, date_from, date_to, groupby, revenue_source,
    ))


def _campaign_dates_uncached(
    db: Session,
    campaign_id: str,
    date_from: date,
    date_to: date,
    groupby: str = "day",
    revenue_source: str = "auto",
) -> List[DateRow]:
    period_expr = _period_expr(groupby)

    sql = text(
        f"SELECT"
        f"  {period_expr}                                                        AS period,"
        "  SUM(g.impressions)                                                   AS impressions,"
        "  SUM(g.clicks)                                                        AS clicks,"
        "  SUM(g.spend_usd)                                                     AS spend_usd,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)                      AS revenue_usd,"
        f" COALESCE(SUM({_cc_share('a.total_sales_usd')}), 0)                 AS total_sales_usd,"
        f" COALESCE(SUM({_cc_share('a.orders')}), 0)                           AS orders,"
        f" COALESCE(SUM({_cc_share('a.units_sold')}), 0)                       AS units_sold,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)         END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                          END AS cpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.clicks)                                            END AS rpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN CAST(COALESCE(SUM({_cc_share('a.orders')}), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                            END AS conv_rate,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "    - SUM(g.spend_usd)                                                 AS profit,"
        f" CASE WHEN SUM(g.spend_usd) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.spend_usd)                                         END AS roas,"
        f" CASE WHEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0) > 0"
        "       THEN SUM(g.spend_usd)"
        f"           / COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)          END AS acos"
        " FROM google_ads_campaign_day g"
        + _archer_join("", revenue_source)
        + _CC_SUBQUERY
        + " WHERE g.campaign_id = :campaign_id"
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
            total_sales_usd=float(r.total_sales_usd or 0),
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
    country_code: str = "",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
    campaign_type_filter: str = "",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    account_filter: str = "",
    revenue_source: str = "auto",
) -> List[TimeseriesPoint]:
    revenue_source = _norm_source(revenue_source)
    key = ("timeseries", date_from, date_to, groupby, country_code, asin_filter,
           campaign_filter, status_filter, campaign_type_filter, age_min, age_max,
           account_filter, revenue_source)
    return cache.get_or_compute(key, lambda: _timeseries_uncached(
        db, date_from, date_to, groupby, country_code, asin_filter, campaign_filter,
        status_filter, campaign_type_filter, age_min, age_max, account_filter,
        revenue_source,
    ))


def _timeseries_uncached(
    db: Session,
    date_from: date,
    date_to: date,
    groupby: str = "day",
    country_code: str = "",
    asin_filter: str = "",
    campaign_filter: str = "",
    status_filter: str = "",
    campaign_type_filter: str = "",
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    account_filter: str = "",
    revenue_source: str = "auto",
) -> List[TimeseriesPoint]:
    period_expr = _period_expr(groupby)
    joins, where, fparams = _filter_clause(
        country_code, asin_filter, campaign_filter,
        status_filter, campaign_type_filter, age_min, age_max, account_filter,
    )

    sql = text(
        f"SELECT"
        f"  {period_expr}                                                        AS period,"
        "  SUM(g.impressions)                                                   AS impressions,"
        "  SUM(g.clicks)                                                        AS clicks,"
        "  SUM(g.spend_usd)                                                     AS spend_usd,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)                      AS revenue_usd,"
        f" COALESCE(SUM({_cc_share('a.total_sales_usd')}), 0)                 AS total_sales_usd,"
        f" COALESCE(SUM({_cc_share('a.orders')}), 0)                           AS orders,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)         END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                          END AS cpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.clicks)                                            END AS rpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN CAST(COALESCE(SUM({_cc_share('a.orders')}), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                            END AS conv_rate,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "    - SUM(g.spend_usd)                                                 AS profit,"
        f" CASE WHEN SUM(g.spend_usd) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.spend_usd)                                         END AS roas"
        " FROM google_ads_campaign_day g"
        + _archer_join(country_code, revenue_source)
        + _CC_SUBQUERY
        + joins
        + " WHERE g.date BETWEEN :date_from AND :date_to"
        + where
        + " GROUP BY period"
        " ORDER BY period ASC"
    )

    params: dict = {"date_from": date_from, "date_to": date_to}
    params.update(fparams)
    rows = db.execute(sql, params).fetchall()

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
            total_sales_usd=float(r.total_sales_usd or 0),
            rpc=_safe_float(r.rpc),
            profit=float(r.profit or 0),
            roas=_safe_float(r.roas),
        )
        for r in rows
    ]


# ── Per-product (halo) breakdown ──────────────────────────────────────────────

def _campaign_asin_type(db: Session, campaign_id: str):
    """Resolve a campaign's own ASIN + type from google_ads_campaign_day."""
    row = db.execute(text(
        "SELECT MAX(asin) AS asin, COALESCE(MAX(campaign_type), 'brand') AS ctype"
        " FROM google_ads_campaign_day WHERE campaign_id = :cid"
    ), {"cid": campaign_id}).fetchone()
    if not row or not row.asin:
        return None, "brand"
    return row.asin.upper(), (row.ctype or "brand")


def get_campaign_products(db: Session, campaign_id: str, date_from: date, date_to: date) -> CampaignProductsResponse:
    """Which ASINs actually sold under a campaign's link (new API), for the range."""
    def _compute():
        own_asin, ctype = _campaign_asin_type(db, campaign_id)
        if not own_asin:
            return CampaignProductsResponse(campaign_id=campaign_id, own_asin=None, products=[])
        rows = db.execute(text(
            "SELECT sold_asin, MAX(sold_product_name) AS name,"
            "       SUM(units) AS units, SUM(purchases) AS purchases,"
            "       SUM(sales) AS sales, SUM(commission) AS commission"
            " FROM archer_link_product_day"
            " WHERE link_asin = :asin AND link_type = :ctype AND geo = 'US'"
            "   AND date BETWEEN :df AND :dt"
            " GROUP BY sold_asin"
            " ORDER BY commission DESC"
        ), {"asin": own_asin, "ctype": ctype, "df": date_from, "dt": date_to}).fetchall()
        total_comm = sum(float(r.commission or 0) for r in rows) or 0.0
        products = [
            CampaignProductRow(
                sold_asin=r.sold_asin,
                product_name=r.name,
                is_own=(r.sold_asin or "").upper() == own_asin,
                units=int(r.units or 0),
                purchases=int(r.purchases or 0),
                sales=float(r.sales or 0),
                commission=float(r.commission or 0),
                pct_of_commission=(float(r.commission or 0) / total_comm) if total_comm > 0 else None,
            )
            for r in rows
        ]
        return CampaignProductsResponse(campaign_id=campaign_id, own_asin=own_asin, products=products)

    return cache.get_or_compute(("campaign_products", campaign_id, date_from, date_to), _compute)


def get_halo_opportunities(db: Session, date_from: date, date_to: date, min_commission: float = 20.0) -> HaloOpportunitiesResponse:
    """
    Campaigns whose revenue is mostly halo (own ASIN ~0, another ASIN dominates).
    Joins per-link product data to google_ads for spend / name / status.
    """
    def _compute():
        # Per (link_asin, link_type): own vs total commission + brand of the link's own ASIN.
        agg = db.execute(text(
            "SELECT link_asin, link_type,"
            "  SUM(commission) AS total_comm,"
            "  SUM(CASE WHEN sold_asin = link_asin THEN commission ELSE 0 END) AS own_comm,"
            "  MAX(CASE WHEN sold_asin = link_asin THEN brand_name END) AS own_brand"
            " FROM archer_link_product_day"
            " WHERE geo = 'US' AND date BETWEEN :df AND :dt"
            " GROUP BY link_asin, link_type"
            " HAVING total_comm >= :minc"
        ), {"df": date_from, "dt": date_to, "minc": min_commission}).fetchall()

        out = []
        for a in agg:
            total = float(a.total_comm or 0)
            own = float(a.own_comm or 0)
            if total <= 0 or own > 0.05 * total:
                continue  # own ASIN still pulls its weight — not an opportunity
            # top non-own sold ASIN for this link
            top = db.execute(text(
                "SELECT sold_asin, MAX(sold_product_name) AS name, MAX(brand_name) AS brand,"
                "       SUM(commission) AS comm, SUM(units) AS units"
                " FROM archer_link_product_day"
                " WHERE link_asin = :la AND link_type = :lt AND geo = 'US'"
                "   AND date BETWEEN :df AND :dt AND sold_asin != :la"
                " GROUP BY sold_asin ORDER BY comm DESC LIMIT 1"
            ), {"la": a.link_asin, "lt": a.link_type, "df": date_from, "dt": date_to}).fetchone()
            if not top:
                continue
            # campaign spend / name / status (latest) for this asin+type
            g = db.execute(text(
                "SELECT g.campaign_id, SUM(g.spend_usd) AS spend,"
                "  MAX(g.campaign_name) AS name,"
                "  (SELECT campaign_status FROM google_ads_campaign_day s"
                "   WHERE s.campaign_id = g.campaign_id AND s.campaign_status IS NOT NULL"
                "   ORDER BY s.date DESC LIMIT 1) AS status"
                " FROM google_ads_campaign_day g"
                " WHERE g.asin = :la AND COALESCE(g.campaign_type,'brand') = :lt"
                "   AND g.date BETWEEN :df AND :dt"
                " GROUP BY g.campaign_id ORDER BY spend DESC LIMIT 1"
            ), {"la": a.link_asin, "lt": a.link_type, "df": date_from, "dt": date_to}).fetchone()
            spend = float(g.spend or 0) if g else 0.0
            out.append(HaloOpportunityRow(
                campaign_id=g.campaign_id if g else None,
                campaign_name=g.name if g else None,
                status=g.status if g else None,
                asin=a.link_asin,
                campaign_type=a.link_type,
                spend_usd=spend,
                own_commission=own,
                total_commission=total,
                roas=(total / spend) if spend > 0 else None,
                top_halo_asin=top.sold_asin,
                top_halo_name=top.name,
                top_halo_commission=float(top.comm or 0),
                top_halo_units=int(top.units or 0),
                same_brand=bool(a.own_brand and top.brand and a.own_brand == top.brand),
            ))
        out.sort(key=lambda x: -x.top_halo_commission)
        return HaloOpportunitiesResponse(rows=out, total=len(out))

    return cache.get_or_compute(("halo_opps", date_from, date_to, min_commission), _compute)


# ── Distinct accounts ─────────────────────────────────────────────────────────

def get_accounts(db: Session) -> List[str]:
    """Distinct non-null account labels, for the dashboard filter + upload datalist."""
    def _compute():
        rows = db.execute(text(
            "SELECT DISTINCT account FROM google_ads_campaign_day"
            " WHERE account IS NOT NULL AND account != ''"
            " ORDER BY account"
        )).fetchall()
        return [r[0] for r in rows]
    return cache.get_or_compute(("accounts",), _compute)


# ── Product warnings (Archer link removed) ────────────────────────────────────

def get_warnings(db: Session) -> List[ProductWarning]:
    """
    Return enabled campaigns whose ASIN is confirmed removed from Archer
    (is_active=0 in archer_asin_status). ASINs not yet verified are excluded
    so the banner only shows actionable, API-confirmed removals.
    """
    sql = text("""
        WITH latest_status AS (
            SELECT g.campaign_id, g.campaign_name, g.asin
            FROM google_ads_campaign_day g
            INNER JOIN (
                SELECT campaign_id, MAX(date) AS max_date
                FROM google_ads_campaign_day
                WHERE campaign_status IS NOT NULL
                GROUP BY campaign_id
            ) ld ON g.campaign_id = ld.campaign_id AND g.date = ld.max_date
            WHERE g.campaign_status = 'Enabled'
              AND g.asin IS NOT NULL
        ),
        archer_last AS (
            SELECT asin, MAX(date) AS last_date
            FROM archer_product_day
            GROUP BY asin
        ),
        max_archer AS (
            SELECT MAX(date) AS max_date FROM archer_product_day
        )
        SELECT DISTINCT
            ls.campaign_name,
            ls.asin,
            al.last_date                                                        AS last_archer_date,
            CAST(julianday(ma.max_date) - julianday(al.last_date) AS INTEGER)  AS days_missing
        FROM latest_status ls
        JOIN archer_last al ON ls.asin = al.asin
        CROSS JOIN max_archer ma
        JOIN archer_asin_status s ON ls.asin = s.asin
        WHERE s.is_active = 0
        ORDER BY al.last_date ASC
    """)
    rows = db.execute(sql).fetchall()
    return [
        ProductWarning(
            campaign_name=r.campaign_name,
            asin=r.asin,
            last_archer_date=str(r.last_archer_date),
            days_missing=int(r.days_missing),
        )
        for r in rows
    ]


# ── Detailed export (all campaigns × date for a given date range) ─────────────

def get_detailed_export(
    db: Session,
    date_from: date,
    date_to: date,
    groupby: str = "day",
    revenue_source: str = "auto",
) -> List[DetailedExportRow]:
    revenue_source = _norm_source(revenue_source)
    period_expr = _period_expr(groupby)

    sql = text(
        f"SELECT"
        f"  g.campaign_id                                                         AS campaign_id,"
        f"  g.campaign_name                                                       AS campaign_name,"
        f"  g.asin                                                                AS asin,"
        f"  {period_expr}                                                         AS period,"
        "  SUM(g.impressions)                                                    AS impressions,"
        "  SUM(g.clicks)                                                         AS clicks,"
        "  SUM(g.spend_usd)                                                      AS spend_usd,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)                       AS revenue_usd,"
        f" COALESCE(SUM({_cc_share('a.orders')}), 0)                            AS orders,"
        f" COALESCE(SUM({_cc_share('a.units_sold')}), 0)                        AS units_sold,"
        "  CASE WHEN SUM(g.impressions) > 0"
        "       THEN CAST(SUM(g.clicks) AS FLOAT) / SUM(g.impressions)          END AS ctr,"
        "  CASE WHEN SUM(g.clicks) > 0"
        "       THEN SUM(g.spend_usd) / SUM(g.clicks)                           END AS cpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.clicks)                                             END AS rpc,"
        f" CASE WHEN SUM(g.clicks) > 0"
        f"      THEN CAST(COALESCE(SUM({_cc_share('a.orders')}), 0) AS FLOAT)"
        "            / SUM(g.clicks)                                             END AS conv_rate,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "    - SUM(g.spend_usd)                                                  AS profit,"
        f" CASE WHEN SUM(g.spend_usd) > 0"
        f"      THEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)"
        "            / SUM(g.spend_usd)                                          END AS roas,"
        f" CASE WHEN COALESCE(SUM({_cc_share('a.revenue_usd')}), 0) > 0"
        "       THEN SUM(g.spend_usd)"
        f"           / COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)           END AS acos"
        " FROM google_ads_campaign_day g"
        + _archer_join("", revenue_source)
        + _CC_SUBQUERY
        + " WHERE g.date BETWEEN :date_from AND :date_to"
        " GROUP BY g.campaign_id, g.campaign_name, g.asin, period"
        " ORDER BY g.campaign_name ASC, period ASC"
    )

    rows = db.execute(sql, {"date_from": date_from, "date_to": date_to}).fetchall()

    return [
        DetailedExportRow(
            campaign_id=str(r.campaign_id),
            campaign_name=str(r.campaign_name),
            asin=r.asin,
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


# ── Revenue diagnostic ────────────────────────────────────────────────────────

def get_revenue_debug(db, date_from, date_to):
    """
    Per-ASIN breakdown: archer DB revenue vs dashboard-attributed revenue.
    Call GET /api/dashboard/debug/revenue?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    """
    sql = text(
        "SELECT"
        "  g.asin,"
        "  COUNT(DISTINCT g.campaign_id)                     AS campaigns,"
        "  MAX(cc.cnt_active)                                AS cc_active,"
        "  MAX(cc.cnt)                                       AS cc_cnt,"
        f" COALESCE(SUM({_cc_share('a.revenue_usd')}), 0)   AS attributed,"
        "  SUM(g.spend_usd)                                  AS spend"
        " FROM google_ads_campaign_day g"
        + _archer_join()
        + _CC_SUBQUERY
        + " WHERE g.date BETWEEN :date_from AND :date_to AND g.asin IS NOT NULL"
        " GROUP BY g.asin"
        " ORDER BY attributed DESC"
    )
    rows = db.execute(sql, {"date_from": date_from, "date_to": date_to}).fetchall()

    archer_sql = text(
        "SELECT asin, SUM(revenue_usd) AS total"
        " FROM archer_product_day"
        # legacy only — with two sources stored, summing both would double-count
        " WHERE date BETWEEN :date_from AND :date_to AND geo = 'US' AND source = 'legacy'"
        " GROUP BY asin"
    )
    archer_rows = db.execute(archer_sql, {"date_from": date_from, "date_to": date_to}).fetchall()
    archer_by_asin = {r.asin: float(r.total) for r in archer_rows}

    items = []
    for r in rows:
        asin = r.asin
        attributed = float(r.attributed or 0)
        archer_rev = archer_by_asin.get(asin, 0.0)
        items.append({
            "asin":          asin,
            "campaigns":     int(r.campaigns or 0),
            "cc_active":     int(r.cc_active or 0),
            "cc_cnt":        int(r.cc_cnt or 0),
            "archer_db_rev": round(archer_rev, 2),
            "dashboard_rev": round(attributed, 2),
            "diff":          round(attributed - archer_rev, 2),
            "spend":         round(float(r.spend or 0), 2),
        })

    total_attributed = sum(i["dashboard_rev"] for i in items)
    total_archer = sum(archer_by_asin.values())

    return {
        "date_from":       str(date_from),
        "date_to":         str(date_to),
        "dashboard_total": round(total_attributed, 2),
        "archer_db_total": round(total_archer, 2),
        "difference":      round(total_attributed - total_archer, 2),
        "note":            "diff>0 = over-counted; look for asins with large positive diff",
        "asins":           sorted(items, key=lambda x: abs(x["diff"]), reverse=True),
    }

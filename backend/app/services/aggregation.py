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

from ..schemas import SummaryResponse, CampaignRow, DateRow, TimeseriesPoint, ProductWarning, DetailedExportRow
from ..utils.geo_utils import country_to_geo

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


# Subquery: per (asin, date) compute
#   cnt_active — campaigns with spend > 0
#   cnt        — effective denominator: cnt_active if any are active, else total count
#                (so revenue is never lost when all campaigns are paused)
_CC_SUBQUERY = (
    " LEFT JOIN ("
    "   SELECT asin, date,"
    "     SUM(CASE WHEN spend_usd > 0 THEN 1 ELSE 0 END) AS cnt_active,"
    "     CASE WHEN SUM(CASE WHEN spend_usd > 0 THEN 1 ELSE 0 END) > 0"
    "          THEN SUM(CASE WHEN spend_usd > 0 THEN 1 ELSE 0 END)"
    "          ELSE COUNT(*)"
    "     END AS cnt"
    "   FROM google_ads_campaign_day"
    "   WHERE date BETWEEN :date_from AND :date_to AND asin IS NOT NULL"
    "   GROUP BY asin, date"
    " ) cc ON g.asin = cc.asin AND g.date = cc.date"
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
def _archer_join(country_code: str = "") -> str:
    if country_code:
        geo = country_to_geo(country_code)
        return f" LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date AND a.geo = '{geo}'"
    return " LEFT JOIN archer_product_day a ON g.asin = a.asin AND a.date = g.date AND a.geo = 'US'"

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

def get_summary(db: Session, date_from: date, date_to: date, country_code: str = "") -> SummaryResponse:
    country_filter = "AND g.country_code = :country_code" if country_code else ""
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
        + _archer_join(country_code)
        + _CC_SUBQUERY
        + f" WHERE g.date BETWEEN :date_from AND :date_to {country_filter}"
    )
    params: dict = {"date_from": date_from, "date_to": date_to}
    if country_code:
        params["country_code"] = country_code
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
        + _archer_join(country_code)
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
        f"  {country_filter}"
        " GROUP BY g.campaign_id"
        f" ORDER BY {sort_col} {dir_sql}"
    )

    params: dict = {
        "date_from": date_from,
        "date_to": date_to,
        "asin": asin_filter,
        "campaign": campaign_filter,
        "status": status_filter,
        "campaign_type_filter": campaign_type_filter,
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
        + _archer_join()
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
) -> List[TimeseriesPoint]:
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
        + _archer_join()
        + _CC_SUBQUERY
        + " WHERE g.date BETWEEN :date_from AND :date_to"
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
            total_sales_usd=float(r.total_sales_usd or 0),
            rpc=_safe_float(r.rpc),
            profit=float(r.profit or 0),
            roas=_safe_float(r.roas),
        )
        for r in rows
    ]


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
) -> List[DetailedExportRow]:
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
        + _archer_join()
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
        " WHERE date BETWEEN :date_from AND :date_to AND geo = 'US'"
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

import { useState, useMemo, useCallback } from "react";
import { TableFilters } from "./TableFilters";
import type { StatusOption } from "./TableFilters";
import { DateDrillDown } from "./DateDrillDown";
import { fmtUSD, fmtROAS, fmtRPC, fmtPct, fmtNumber } from "../../utils/formatters";
import type { CampaignRow, DateRow, GroupBy, DateRange, SortDir } from "../../types";

type SortKey = keyof Pick<
  CampaignRow,
  | "campaign_name"
  | "impressions"
  | "clicks"
  | "ctr"
  | "spend_usd"
  | "cpc"
  | "orders"
  | "conv_rate"
  | "revenue_usd"
  | "rpc"
  | "profit"
  | "roas"
>;

interface Props {
  rows: CampaignRow[];
  loading: boolean;
  dateRange: DateRange;
  groupby: GroupBy;
  onExport: (filteredRows: CampaignRow[]) => void;
  /** Shared date-row cache, so ExportModal can access all fetched date data */
  dateDataRef: React.MutableRefObject<Record<string, DateRow[]>>;
}

const COL_SPAN = 17; // toggle + Campaign + Status + Age + 13 metric columns

function ageDays(firstSeen: string | null): number | null {
  if (!firstSeen) return null;
  return Math.floor((Date.now() - new Date(firstSeen).getTime()) / 86_400_000);
}

function fmtAge(days: number | null): string {
  if (days === null) return "—";
  if (days < 30) return `${days}d`;
  if (days < 365) return `${Math.round(days / 30)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

export function CampaignTable({ rows, loading, dateRange, groupby, onExport, dateDataRef }: Props) {
  const [campaignFilter, setCampaignFilter] = useState("");
  const [asinFilter, setAsinFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusOption>("All");
  const [ageMin, setAgeMin]             = useState<number | "">("");
  const [ageMax, setAgeMax]             = useState<number | "">("");
  const [sortKey, setSortKey]       = useState<SortKey>("spend_usd");
  const [sortDir, setSortDir]       = useState<SortDir>("desc");
  const [expanded, setExpanded]     = useState<Set<string>>(new Set());

  const toggleSort = useCallback((key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }, [sortKey]);

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const filtered = useMemo(() => {
    let data = rows;
    if (campaignFilter) {
      const q = campaignFilter.toLowerCase();
      data = data.filter((r) => r.campaign_name.toLowerCase().includes(q));
    }
    if (asinFilter) {
      const q = asinFilter.toLowerCase();
      data = data.filter((r) => r.asin?.toLowerCase().includes(q) ?? false);
    }
    if (statusFilter !== "All") {
      data = data.filter((r) => r.current_status === statusFilter);
    }
    if (ageMin !== "" || ageMax !== "") {
      data = data.filter((r) => {
        const d = ageDays(r.first_seen);
        if (d === null) return false;
        if (ageMin !== "" && d < ageMin) return false;
        if (ageMax !== "" && d > ageMax) return false;
        return true;
      });
    }
    return [...data].sort((a, b) => {
      const av = (a[sortKey] as number) ?? 0;
      const bv = (b[sortKey] as number) ?? 0;
      // string sort for campaign_name / asin
      if (typeof av === "string") {
        return sortDir === "asc"
          ? String(av).localeCompare(String(bv))
          : String(bv).localeCompare(String(av));
      }
      return sortDir === "asc" ? av - bv : bv - av;
    });
  }, [rows, campaignFilter, asinFilter, statusFilter, ageMin, ageMax, sortKey, sortDir]);

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span className="ml-1 text-gray-300">↕</span>;
    return <span className="ml-1 text-blue-500">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  const totImpressions = filtered.reduce((s, r) => s + r.impressions, 0);
  const totClicks      = filtered.reduce((s, r) => s + r.clicks, 0);
  const totSpend       = filtered.reduce((s, r) => s + r.spend_usd, 0);
  const totOrders      = filtered.reduce((s, r) => s + r.orders, 0);
  const totRevenue     = filtered.reduce((s, r) => s + r.revenue_usd, 0);
  const totProfit      = totRevenue - totSpend;
  const totCtr         = totImpressions > 0 ? totClicks / totImpressions : null;
  const totCpc         = totClicks > 0 ? totSpend / totClicks : null;
  const totCpa         = totOrders > 0 ? totSpend / totOrders : null;
  const totConvRate    = totClicks > 0 ? totOrders / totClicks : null;
  const totRpc         = totClicks > 0 ? totRevenue / totClicks : null;
  const totAov         = totOrders > 0 ? totRevenue / totOrders : null;
  const totRoas        = totSpend > 0 ? totRevenue / totSpend : null;

  const thBase = "px-1.5 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider select-none whitespace-nowrap";
  const thSort = `${thBase} cursor-pointer hover:bg-gray-100`;
  const tdBase = "px-1.5 py-1.5 text-xs text-gray-800 whitespace-nowrap";
  const tfBase = "px-1.5 py-2 text-right text-xs font-semibold text-gray-700 whitespace-nowrap bg-gray-50";

  if (loading) {
    return <div className="bg-white rounded-lg border border-gray-200 p-5 h-48 animate-pulse" />;
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      {/* Toolbar: filters + export */}
      <div className="p-4 border-b border-gray-200 flex flex-wrap items-center justify-between gap-3">
        <TableFilters
          campaignFilter={campaignFilter}
          asinFilter={asinFilter}
          statusFilter={statusFilter}
          ageMin={ageMin}
          ageMax={ageMax}
          onCampaignChange={setCampaignFilter}
          onAsinChange={setAsinFilter}
          onStatusChange={setStatusFilter}
          onAgeMinChange={setAgeMin}
          onAgeMaxChange={setAgeMax}
        />
        <button
          onClick={() => onExport(filtered)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 transition-colors"
        >
          ↓ Export CSV
        </button>
      </div>

      <div className="overflow-auto max-h-[600px]">
        <table className="w-full">
          <thead className="sticky top-0 z-10 bg-gray-50 border-b border-gray-200">
            <tr>
              <th className={thBase} style={{ width: 20 }} />
              <th className={thSort} style={{ minWidth: 140, maxWidth: 220 }} onClick={() => toggleSort("campaign_name")}>
                Campaign <SortIcon col="campaign_name" />
              </th>
              <th className={`${thBase} text-center`} style={{ minWidth: 58 }}>Status</th>
              <th className={`${thBase} text-right`} style={{ minWidth: 46 }}>Age</th>
              <th className={`${thSort} text-right`} style={{ minWidth: 60 }} onClick={() => toggleSort("impressions")}>
                Impr. <SortIcon col="impressions" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 50 }} onClick={() => toggleSort("clicks")}>
                Clicks <SortIcon col="clicks" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 44 }} onClick={() => toggleSort("ctr")}>
                CTR <SortIcon col="ctr" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 62 }} onClick={() => toggleSort("spend_usd")}>
                Cost <SortIcon col="spend_usd" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 56 }} onClick={() => toggleSort("cpc")}>
                CPC <SortIcon col="cpc" />
              </th>
              <th className={`${thBase} text-right`} style={{ minWidth: 56 }}>CPA</th>
              <th className={`${thSort} text-right`} style={{ minWidth: 50 }} onClick={() => toggleSort("orders")}>
                Orders <SortIcon col="orders" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 48 }} onClick={() => toggleSort("conv_rate")}>
                Conv% <SortIcon col="conv_rate" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 66 }} onClick={() => toggleSort("revenue_usd")}>
                Revenue <SortIcon col="revenue_usd" />
              </th>
              <th className={`${thBase} text-right`} style={{ minWidth: 56 }}>AOV</th>
              <th className={`${thSort} text-right`} style={{ minWidth: 52 }} onClick={() => toggleSort("rpc")}>
                RPC <SortIcon col="rpc" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 62 }} onClick={() => toggleSort("profit")}>
                Profit <SortIcon col="profit" />
              </th>
              <th className={`${thSort} text-right`} style={{ minWidth: 50 }} onClick={() => toggleSort("roas")}>
                ROAS <SortIcon col="roas" />
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={COL_SPAN} className="px-4 py-8 text-center text-gray-400 text-sm">
                  No campaigns found
                </td>
              </tr>
            )}
            {filtered.map((row) => {
              const isOpen = expanded.has(row.campaign_id);
              return (
                <>
                  {/* Campaign-level row (Level 1) */}
                  <tr
                    key={row.campaign_id}
                    className="hover:bg-gray-50 transition-colors cursor-pointer"
                    onClick={() => toggleExpand(row.campaign_id)}
                  >
                    {/* expand toggle */}
                    <td className={`${tdBase} text-center text-gray-400 select-none`}>
                      {isOpen ? "▾" : "▸"}
                    </td>
                    <td className={tdBase} style={{ maxWidth: 240 }}>
                      <div className="truncate font-medium" title={row.campaign_name}>
                        {row.campaign_name}
                      </div>
                      {row.asin && (
                        <div className="font-mono text-gray-400 text-[10px] leading-tight">
                          {row.asin}
                        </div>
                      )}
                    </td>
                    <td className={`${tdBase} text-center`}>
                      {row.current_status ? (
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          row.current_status === "Enabled"
                            ? "bg-green-100 text-green-700"
                            : row.current_status === "Paused"
                            ? "bg-yellow-100 text-yellow-700"
                            : "bg-gray-100 text-gray-500"
                        }`}>
                          {row.current_status}
                        </span>
                      ) : "—"}
                    </td>
                    <td className={`${tdBase} text-right`}>{fmtAge(ageDays(row.first_seen))}</td>
                    <td className={`${tdBase} text-right`}>{fmtNumber(row.impressions)}</td>
                    <td className={`${tdBase} text-right`}>{fmtNumber(row.clicks)}</td>
                    <td className={`${tdBase} text-right`}>{fmtPct(row.ctr)}</td>
                    <td className={`${tdBase} text-right`}>{fmtUSD(row.spend_usd)}</td>
                    <td className={`${tdBase} text-right`}>{fmtUSD(row.cpc)}</td>
                    <td className={`${tdBase} text-right`}>{fmtUSD(row.orders > 0 ? row.spend_usd / row.orders : null)}</td>
                    <td className={`${tdBase} text-right`}>{fmtNumber(row.orders)}</td>
                    <td className={`${tdBase} text-right`}>{fmtPct(row.conv_rate)}</td>
                    <td className={`${tdBase} text-right`}>{fmtUSD(row.revenue_usd)}</td>
                    <td className={`${tdBase} text-right`}>{fmtUSD(row.orders > 0 ? row.revenue_usd / row.orders : null)}</td>
                    <td className={`${tdBase} text-right`}>{fmtRPC(row.rpc)}</td>
                    <td className={`${tdBase} text-right font-medium ${row.profit > 0 ? "text-green-600" : row.profit < 0 ? "text-red-500" : ""}`}>
                      {fmtUSD(row.profit)}
                    </td>
                    <td className={`${tdBase} text-right font-medium ${(row.roas ?? 0) > 1 ? "text-green-600" : (row.roas ?? 0) < 1 && row.roas != null ? "text-red-500" : ""}`}>
                      {fmtROAS(row.roas)}
                    </td>
                  </tr>

                  {/* Date drill-down rows (Level 2) — only shown when expanded */}
                  {isOpen && (
                    <DateDrillDown
                      key={`dates-${row.campaign_id}`}
                      campaignId={row.campaign_id}
                      dateFrom={dateRange.from}
                      dateTo={dateRange.to}
                      groupby={groupby}
                      colSpan={COL_SPAN}
                      onDataLoaded={(dates) => {
                        dateDataRef.current[row.campaign_id] = dates;
                      }}
                    />
                  )}
                </>
              );
            })}
          </tbody>
          {filtered.length > 0 && (
            <tfoot className="sticky bottom-0 z-10 border-t-2 border-gray-300">
              <tr>
                <td className="px-2 py-2 bg-gray-50" />
                <td className="px-2 py-2 text-xs font-semibold text-gray-700 bg-gray-50">Total</td>
                <td className={tfBase} />
                <td className={tfBase} />
                <td className={tfBase}>{fmtNumber(totImpressions)}</td>
                <td className={tfBase}>{fmtNumber(totClicks)}</td>
                <td className={tfBase}>{fmtPct(totCtr)}</td>
                <td className={tfBase}>{fmtUSD(totSpend)}</td>
                <td className={tfBase}>{fmtUSD(totCpc)}</td>
                <td className={tfBase}>{fmtUSD(totCpa)}</td>
                <td className={tfBase}>{fmtNumber(totOrders)}</td>
                <td className={tfBase}>{fmtPct(totConvRate)}</td>
                <td className={tfBase}>{fmtUSD(totRevenue)}</td>
                <td className={tfBase}>{fmtUSD(totAov)}</td>
                <td className={tfBase}>{fmtRPC(totRpc)}</td>
                <td className={`${tfBase} ${totProfit > 0 ? "text-green-600" : totProfit < 0 ? "text-red-500" : ""}`}>{fmtUSD(totProfit)}</td>
                <td className={`${tfBase} ${(totRoas ?? 0) > 1 ? "text-green-600" : (totRoas ?? 0) < 1 && totRoas != null ? "text-red-500" : ""}`}>{fmtROAS(totRoas)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      <div className="px-4 py-2 border-t border-gray-100 text-xs text-gray-400">
        {filtered.length} campaigns
      </div>
    </div>
  );
}

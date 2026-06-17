import { useState, useEffect, useCallback } from "react";
import { fetchHaloOpportunities } from "../../api/client";
import { fmtUSD, fmtROAS } from "../../utils/formatters";
import type { HaloOpportunity } from "../../types";

interface Props {
  /** Pre-fill + jump to the Create Campaigns tab for a halo ASIN. */
  onCreateForAsin: (asin: string, productName: string | null) => void;
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

// Archer's new attribution (the halo data) only exists from this date.
const CUTOVER = "2026-06-07";

export function OpportunitiesPage({ onCreateForAsin }: Props) {
  const [dateFrom, setDateFrom] = useState(CUTOVER);
  const [dateTo, setDateTo] = useState(daysAgo(1));
  const [rows, setRows] = useState<HaloOpportunity[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchHaloOpportunities(dateFrom, dateTo);
      setRows(r.rows);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const th = "px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const td = "px-3 py-2 text-sm text-gray-700 whitespace-nowrap";

  return (
    <div className="space-y-6 p-4">
      <div>
        <h2 className="text-xl font-semibold text-gray-800">Halo Opportunities</h2>
        <p className="text-sm text-gray-500 mt-1">
          Campaigns whose revenue comes almost entirely from <strong>other</strong> ASINs (halo),
          not the one they advertise — candidates to re-target. New-API data only (from Jun 7).
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-gray-100">
          <span className="text-xs text-gray-500">Range</span>
          <input type="date" value={dateFrom} min={CUTOVER}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1 text-sm" />
          <span className="text-gray-400 text-sm">to</span>
          <input type="date" value={dateTo} min={CUTOVER}
            onChange={(e) => setDateTo(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1 text-sm" />
          <span className="ml-auto text-xs text-amber-600">
            ⚠ Recent days still settling — numbers will rise.
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className={th}>Campaign</th>
                <th className={th}>Status</th>
                <th className={`${th} text-right`}>Spend</th>
                <th className={`${th} text-right`}>Own ASIN $</th>
                <th className={`${th} text-right`}>Total $</th>
                <th className={`${th} text-right`}>ROAS</th>
                <th className={th}>Top selling ASIN (halo)</th>
                <th className={`${th} text-right`}>Halo $</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-400 text-sm">Loading…</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-400 text-sm">
                  No halo opportunities in this range.
                </td></tr>
              )}
              {!loading && rows.map((o) => (
                <tr key={`${o.asin}-${o.campaign_type}`} className="hover:bg-gray-50">
                  <td className={`${td} max-w-xs truncate`} title={o.campaign_name ?? ""}>
                    {o.campaign_name ?? "—"}
                    <span className="block font-mono text-[10px] text-gray-400">{o.asin}</span>
                  </td>
                  <td className={td}>
                    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      o.status === "Enabled" ? "bg-green-100 text-green-700"
                      : o.status === "Paused" ? "bg-yellow-100 text-yellow-700"
                      : "bg-gray-100 text-gray-500"}`}>
                      {o.status ?? "—"}
                    </span>
                  </td>
                  <td className={`${td} text-right`}>{fmtUSD(o.spend_usd)}</td>
                  <td className={`${td} text-right ${o.own_commission === 0 ? "text-red-500 font-medium" : ""}`}>
                    {fmtUSD(o.own_commission)}
                  </td>
                  <td className={`${td} text-right`}>{fmtUSD(o.total_commission)}</td>
                  <td className={`${td} text-right font-medium ${(o.roas ?? 0) > 1 ? "text-green-600" : "text-red-500"}`}>
                    {fmtROAS(o.roas)}
                  </td>
                  <td className={`${td} max-w-xs truncate`} title={o.top_halo_name ?? ""}>
                    <span className="font-mono text-xs">{o.top_halo_asin}</span>
                    {o.same_brand
                      ? <span className="ml-1.5 inline-block px-1 py-0.5 rounded text-[9px] bg-blue-100 text-blue-700">variant swap</span>
                      : <span className="ml-1.5 inline-block px-1 py-0.5 rounded text-[9px] bg-purple-100 text-purple-700">cross-sell</span>}
                    <span className="block text-[10px] text-gray-400 truncate">{o.top_halo_name ?? ""}</span>
                  </td>
                  <td className={`${td} text-right font-medium`}>{fmtUSD(o.top_halo_commission)}</td>
                  <td className={`${td} text-right`}>
                    <button
                      onClick={() => onCreateForAsin(o.top_halo_asin, o.top_halo_name)}
                      className="px-2 py-1 text-xs font-medium rounded border border-blue-300 text-blue-600 hover:bg-blue-50 whitespace-nowrap"
                    >
                      🚀 Create campaign
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && rows.length > 0 && (
          <div className="px-4 py-2 border-t border-gray-100 text-xs text-gray-400">
            {rows.length} opportunities. "Variant swap" = same brand (likely re-target safely);
            "cross-sell" = different product (validate before cutting the original).
          </div>
        )}
      </div>
    </div>
  );
}

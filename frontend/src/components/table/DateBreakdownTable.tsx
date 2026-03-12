import { fmtUSD, fmtROAS, fmtRPC, fmtPct, fmtNumber } from "../../utils/formatters";
import type { TimeseriesPoint } from "../../types";

interface Props {
  points: TimeseriesPoint[];
  loading: boolean;
}

export function DateBreakdownTable({ points, loading }: Props) {
  if (loading) {
    return <div className="bg-white rounded-lg border border-gray-200 p-5 h-32 animate-pulse" />;
  }

  if (!points.length) {
    return null;
  }

  const totImpressions = points.reduce((s, r) => s + r.impressions, 0);
  const totClicks      = points.reduce((s, r) => s + r.clicks, 0);
  const totSpend       = points.reduce((s, r) => s + r.spend_usd, 0);
  const totOrders      = points.reduce((s, r) => s + r.orders, 0);
  const totRevenue     = points.reduce((s, r) => s + r.revenue_usd, 0);
  const totProfit      = totRevenue - totSpend;
  const totCtr         = totImpressions > 0 ? totClicks / totImpressions : null;
  const totCpc         = totClicks > 0 ? totSpend / totClicks : null;
  const totCpa         = totOrders > 0 ? totSpend / totOrders : null;
  const totConvRate    = totClicks > 0 ? totOrders / totClicks : null;
  const totRpc         = totClicks > 0 ? totRevenue / totClicks : null;
  const totAov         = totOrders > 0 ? totRevenue / totOrders : null;
  const totRoas        = totSpend > 0 ? totRevenue / totSpend : null;

  const th = "px-3 py-2 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const thL = "px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const td = "px-3 py-2 text-right text-sm text-gray-800 whitespace-nowrap";
  const tdL = "px-3 py-2 text-left text-sm text-gray-700 whitespace-nowrap font-mono";
  const tfBase = "px-3 py-2 text-right text-xs font-semibold text-gray-700 whitespace-nowrap bg-gray-50";

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-700">Date Breakdown</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className={thL}>Period</th>
              <th className={th}>Impressions</th>
              <th className={th}>Clicks</th>
              <th className={th}>CTR</th>
              <th className={th}>Cost</th>
              <th className={th}>CPC</th>
              <th className={th}>CPA</th>
              <th className={th}>Orders</th>
              <th className={th}>Conv. Rate</th>
              <th className={th}>Revenue</th>
              <th className={th}>AOV</th>
              <th className={th}>RPC</th>
              <th className={th}>Profit</th>
              <th className={th}>ROAS</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {points.map((row) => (
              <tr key={row.period} className="hover:bg-gray-50 transition-colors">
                <td className={tdL}>{row.period}</td>
                <td className={td}>{fmtNumber(row.impressions)}</td>
                <td className={td}>{fmtNumber(row.clicks)}</td>
                <td className={td}>{fmtPct(row.ctr)}</td>
                <td className={td}>{fmtUSD(row.spend_usd)}</td>
                <td className={td}>{fmtUSD(row.cpc)}</td>
                <td className={td}>{fmtUSD(row.orders > 0 ? row.spend_usd / row.orders : null)}</td>
                <td className={td}>{fmtNumber(row.orders)}</td>
                <td className={td}>{fmtPct(row.conv_rate)}</td>
                <td className={td}>{fmtUSD(row.revenue_usd)}</td>
                <td className={td}>{fmtUSD(row.orders > 0 ? row.revenue_usd / row.orders : null)}</td>
                <td className={td}>{fmtRPC(row.rpc)}</td>
                <td className={`${td} font-medium ${row.profit > 0 ? "text-green-600" : row.profit < 0 ? "text-red-500" : ""}`}>
                  {fmtUSD(row.profit)}
                </td>
                <td className={`${td} font-medium ${(row.roas ?? 0) > 1 ? "text-green-600" : (row.roas ?? 0) < 1 && row.roas != null ? "text-red-500" : ""}`}>
                  {fmtROAS(row.roas)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-gray-300">
            <tr>
              <td className="px-3 py-2 text-left text-xs font-semibold text-gray-700 whitespace-nowrap bg-gray-50">Total</td>
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
        </table>
      </div>
      <div className="px-4 py-2 border-t border-gray-100 text-xs text-gray-400">
        {points.length} {points.length === 1 ? "period" : "periods"}
      </div>
    </div>
  );
}

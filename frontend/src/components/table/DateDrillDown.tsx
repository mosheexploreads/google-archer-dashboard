import { useEffect } from "react";
import { useCampaignDates } from "../../hooks/useCampaignDates";
import { fmtUSD, fmtROAS, fmtRPC, fmtPct, fmtNumber } from "../../utils/formatters";
import type { DateRow, GroupBy } from "../../types";

interface Props {
  campaignId: string;
  dateFrom: string;
  dateTo: string;
  groupby: GroupBy;
  colSpan: number;
  onDataLoaded?: (dates: DateRow[]) => void;
}

export function DateDrillDown({ campaignId, dateFrom, dateTo, groupby, colSpan, onDataLoaded }: Props) {
  const { dates, isLoading } = useCampaignDates(campaignId, dateFrom, dateTo, groupby);

  useEffect(() => {
    if (!isLoading && dates.length > 0) {
      onDataLoaded?.(dates);
    }
  }, [dates, isLoading, onDataLoaded]);

  if (isLoading) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-8 py-3 text-xs text-gray-400 bg-blue-50/30">
          Loading…
        </td>
      </tr>
    );
  }

  if (!dates.length) {
    return (
      <tr>
        <td colSpan={colSpan} className="px-8 py-3 text-xs text-gray-400 bg-blue-50/30 italic">
          No date data available
        </td>
      </tr>
    );
  }

  const tdBase = "px-2 py-1.5 text-xs text-gray-600 whitespace-nowrap bg-blue-50/30";

  return (
    <>
      {dates.map((row) => (
        <tr key={row.period} className="border-b border-blue-100/50">
          {/* indent cell */}
          <td className={`${tdBase} text-gray-300 text-center`}>└</td>
          {/* period in Campaign column */}
          <td className={`${tdBase} font-mono text-gray-500`}>{row.period}</td>
          <td className={`${tdBase} text-right`}>{fmtNumber(row.impressions)}</td>
          <td className={`${tdBase} text-right`}>{fmtNumber(row.clicks)}</td>
          <td className={`${tdBase} text-right`}>{fmtPct(row.ctr)}</td>
          <td className={`${tdBase} text-right`}>{fmtUSD(row.spend_usd)}</td>
          <td className={`${tdBase} text-right`}>{fmtUSD(row.cpc)}</td>
          <td className={`${tdBase} text-right`}>{fmtNumber(row.orders)}</td>
          <td className={`${tdBase} text-right`}>{fmtPct(row.conv_rate)}</td>
          <td className={`${tdBase} text-right`}>{fmtUSD(row.revenue_usd)}</td>
          <td className={`${tdBase} text-right`}>{fmtRPC(row.rpc)}</td>
          <td className={`${tdBase} text-right font-medium ${row.profit > 0 ? "text-green-600" : row.profit < 0 ? "text-red-500" : ""}`}>
            {fmtUSD(row.profit)}
          </td>
          <td className={`${tdBase} text-right font-medium ${(row.roas ?? 0) > 1 ? "text-green-600" : (row.roas ?? 0) < 1 && row.roas != null ? "text-red-500" : ""}`}>
            {fmtROAS(row.roas)}
          </td>
        </tr>
      ))}
    </>
  );
}

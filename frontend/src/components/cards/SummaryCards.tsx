import { MetricCard } from "./MetricCard";
import { fmtUSD, fmtROAS, fmtRPC, fmtNumber } from "../../utils/formatters";
import type { SummaryData } from "../../types";

interface Props {
  data: SummaryData | null;
  loading: boolean;
}

export function SummaryCards({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-5 h-24 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <MetricCard
        label="Total Spend"
        value={fmtUSD(data?.spend_usd ?? null)}
        subValue={data ? `${fmtNumber(data.clicks)} clicks` : undefined}
      />
      <MetricCard
        label="Revenue"
        value={fmtUSD(data?.revenue_usd ?? null)}
        subValue={data ? `${fmtNumber(data.orders)} orders` : undefined}
      />
      <MetricCard
        label="ROAS"
        value={fmtROAS(data?.roas ?? null)}
        subValue={data ? `${fmtNumber(data.impressions)} impressions` : undefined}
      />
      <MetricCard
        label="RPC"
        value={fmtRPC(data?.rpc ?? null)}
        subValue={data ? `${fmtNumber(data.units_sold)} units sold` : undefined}
      />
    </div>
  );
}

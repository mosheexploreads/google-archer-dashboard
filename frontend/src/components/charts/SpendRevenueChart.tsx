import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { fmtUSD, fmtROAS } from "../../utils/formatters";
import type { TimeseriesPoint } from "../../types";

interface Props {
  data: TimeseriesPoint[];
  loading: boolean;
}

function CustomTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-lg text-sm">
      <p className="font-semibold text-gray-800 mb-2">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex justify-between gap-4">
          <span style={{ color: entry.color }}>{entry.name}</span>
          <span className="font-medium">
            {entry.name === "ROAS" ? fmtROAS(entry.value) : fmtUSD(entry.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function SpendRevenueChart({ data, loading }: Props) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-5 h-72 animate-pulse" />
    );
  }

  if (!data.length) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-5 h-72 flex items-center justify-center text-gray-400">
        No data for selected range
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-gray-700 mb-4">Spend vs Revenue</h2>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 5, right: 30, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="period" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="usd"
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            tick={{ fontSize: 12 }}
          />
          <YAxis
            yAxisId="roas"
            orientation="right"
            tickFormatter={(v) => `${v.toFixed(1)}x`}
            tick={{ fontSize: 12 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Bar yAxisId="usd" dataKey="spend_usd" name="Spend" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          <Bar yAxisId="usd" dataKey="revenue_usd" name="Revenue" fill="#10b981" radius={[3, 3, 0, 0]} />
          <Line
            yAxisId="roas"
            type="monotone"
            dataKey="roas"
            name="ROAS"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={{ r: 4 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

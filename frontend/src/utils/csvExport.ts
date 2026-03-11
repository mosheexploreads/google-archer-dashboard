import type { CampaignRow, DateRow, DateRange } from "../types";

interface Column {
  key: string;
  label: string;
}

const METRIC_COLUMNS: Column[] = [
  { key: "impressions",  label: "Impressions" },
  { key: "clicks",       label: "Clicks" },
  { key: "ctr",          label: "CTR" },
  { key: "spend_usd",    label: "Cost (USD)" },
  { key: "cpc",          label: "CPC (USD)" },
  { key: "cpa",          label: "CPA (USD)" },
  { key: "orders",       label: "Orders" },
  { key: "conv_rate",    label: "Conv. Rate" },
  { key: "revenue_usd",  label: "Revenue (USD)" },
  { key: "aov",          label: "AOV (USD)" },
  { key: "rpc",          label: "RPC (USD)" },
  { key: "profit",       label: "Profit (USD)" },
  { key: "roas",         label: "ROAS" },
];

const CAMPAIGN_COLUMNS: Column[] = [
  { key: "campaign_name",   label: "Campaign" },
  { key: "asin",            label: "ASIN" },
  { key: "current_status",  label: "Status" },
  ...METRIC_COLUMNS,
];

const DATE_COLUMNS: Column[] = [
  { key: "campaign_name", label: "Campaign" },
  { key: "asin",          label: "ASIN" },
  { key: "period",        label: "Period" },
  ...METRIC_COLUMNS,
];

function escapeCell(v: unknown): string {
  if (v == null) return "";
  const s = String(v);
  return /[,\n"]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCSV(rows: Record<string, unknown>[], columns: Column[], filename: string) {
  const header = columns.map((c) => c.label).join(",");
  const body = rows
    .map((row) => columns.map((c) => escapeCell(row[c.key])).join(","))
    .join("\n");
  const blob = new Blob([header + "\n" + body], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function addDerived(orders: number, spend_usd: number, revenue_usd: number) {
  return {
    cpa: orders > 0 ? spend_usd / orders : null,
    aov: orders > 0 ? revenue_usd / orders : null,
  };
}

export function exportAggregated(campaigns: CampaignRow[], dateRange: DateRange) {
  const rows = campaigns.map((c) => ({
    ...c,
    ...addDerived(c.orders, c.spend_usd, c.revenue_usd),
  }));
  downloadCSV(
    rows as unknown as Record<string, unknown>[],
    CAMPAIGN_COLUMNS,
    `ads-dashboard-campaigns-${dateRange.from}-to-${dateRange.to}.csv`
  );
}

export function exportDetailed(
  campaigns: CampaignRow[],
  dateData: Record<string, DateRow[]>,
  dateRange: DateRange
) {
  const rows = campaigns.flatMap((c) =>
    (dateData[c.campaign_id] ?? []).map((d) => ({
      campaign_name: c.campaign_name,
      asin: c.asin,
      ...d,
      ...addDerived(d.orders, d.spend_usd, d.revenue_usd),
    }))
  );
  downloadCSV(
    rows as unknown as Record<string, unknown>[],
    DATE_COLUMNS,
    `ads-dashboard-detailed-${dateRange.from}-to-${dateRange.to}.csv`
  );
}

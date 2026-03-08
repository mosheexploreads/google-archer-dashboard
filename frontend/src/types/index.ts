export type GroupBy = "day" | "week" | "month";

export type SortDir = "asc" | "desc";

// ── Sync ─────────────────────────────────────────────────────────────────────

export interface SyncSourceStatus {
  source: string;
  last_sync: string | null;
  last_status: string | null;
  rows_last_sync: number | null;
}

export interface SyncStatus {
  google_ads: SyncSourceStatus;
  archer: SyncSourceStatus;
  next_run: string | null;
  is_syncing: boolean;
}

// ── Summary ───────────────────────────────────────────────────────────────────

export interface SummaryData {
  date_from: string;
  date_to: string;
  spend_usd: number;
  revenue_usd: number;
  orders: number;
  units_sold: number;
  clicks: number;
  impressions: number;
  roas: number | null;
  rpc: number | null;
  acos: number | null;
}

// ── Campaigns ────────────────────────────────────────────────────────────────

export interface CampaignRow {
  campaign_id: string;
  campaign_name: string;
  asin: string | null;
  product_name: string | null;
  impressions: number;
  clicks: number;
  ctr: number | null;
  spend_usd: number;
  cpc: number | null;
  orders: number;
  conv_rate: number | null;
  revenue_usd: number;
  rpc: number | null;
  profit: number;
  roas: number | null;
  acos: number | null;
  units_sold: number;
  current_status: string | null;
}

export interface CampaignsData {
  rows: CampaignRow[];
  total: number;
}

// ── Date drill-down ───────────────────────────────────────────────────────────

export interface DateRow {
  period: string;
  impressions: number;
  clicks: number;
  ctr: number | null;
  spend_usd: number;
  cpc: number | null;
  orders: number;
  conv_rate: number | null;
  revenue_usd: number;
  rpc: number | null;
  profit: number;
  roas: number | null;
  acos: number | null;
  units_sold: number;
}

export interface CampaignDatesData {
  campaign_id: string;
  dates: DateRow[];
}

// ── Timeseries ────────────────────────────────────────────────────────────────

export interface TimeseriesPoint {
  period: string;
  impressions: number;
  clicks: number;
  ctr: number | null;
  spend_usd: number;
  cpc: number | null;
  orders: number;
  conv_rate: number | null;
  revenue_usd: number;
  rpc: number | null;
  profit: number;
  roas: number | null;
}

export interface TimeseriesData {
  points: TimeseriesPoint[];
}

// ── Warnings ──────────────────────────────────────────────────────────────────

export interface ProductWarning {
  campaign_name: string;
  asin: string;
  last_archer_date: string;
  days_missing: number;
}

// ── UI helpers ────────────────────────────────────────────────────────────────

export interface DateRange {
  from: string; // YYYY-MM-DD
  to: string;   // YYYY-MM-DD
}

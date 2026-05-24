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
  country_code: string | null;
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
  first_seen: string | null;
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

// ── Detailed export ───────────────────────────────────────────────────────────

export interface DetailedExportRow {
  campaign_id: string;
  campaign_name: string;
  asin: string | null;
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

// ── Testing ───────────────────────────────────────────────────────────────────

export type TestAction =
  | "testing"
  | "cut"
  | "scale_bid"
  | "mature_bid"
  | "no_data"
  | "completed";

export interface TestCampaignStatus {
  id: number;
  batch_id: number;
  batch_name: string;
  campaign_name: string;
  asin: string | null;
  expected_aov: number;
  cut_threshold: number;
  clicks: number;
  orders: number;
  spend_usd: number;
  revenue_usd: number;
  rpc: number | null;
  cpc: number | null;
  action: TestAction;
  new_bid: number | null;
  action_reason: string;
}

export interface TestStatusData {
  campaigns: TestCampaignStatus[];
  total: number;
  needs_action: number;
}

export interface TestBatchUploadResult {
  batch_id: number;
  batch_name: string;
  campaigns_added: number;
  message: string;
}

// ── UI helpers ────────────────────────────────────────────────────────────────

export interface DateRange {
  from: string; // YYYY-MM-DD
  to: string;   // YYYY-MM-DD
}

// ── Product Catalog ───────────────────────────────────────────────────────────

export interface ProductCatalogItem {
  asin: string;
  country_code: string;
  product_name: string | null;
  price: number | null;
  rating: number | null;
  review_count: number | null;
  image_url: string | null;
  availability: string | null;
  affiliate_url: string | null;
  last_synced_at: string | null;
}

export interface ProductCatalogData {
  items: ProductCatalogItem[];
  total: number;
}

export interface CatalogSyncStatus {
  country_code: string;
  last_synced_at: string | null;
  records: number;
}

// ── Campaign Drafts ───────────────────────────────────────────────────────────

export interface CampaignDraft {
  id: number;
  asin: string;
  country_code: string;
  product_name: string | null;
  attribution_link: string | null;
  campaign_name: string;
  suggested_bid: number;
  status: "draft" | "exported";
  created_at: string | null;
}

export interface CampaignDraftsData {
  drafts: CampaignDraft[];
  total: number;
}

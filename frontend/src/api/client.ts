import axios from "axios";
import type {
  SummaryData,
  CampaignsData,
  CampaignDatesData,
  TimeseriesData,
  SyncStatus,
  GroupBy,
  DetailedExportRow,
  TestStatusData,
  TestBatchUploadResult,
  ProductCatalogData,
  CatalogSyncStatus,
  CampaignDraft,
  CampaignDraftsData,
  CampaignCreatorJob,
  CampaignCreatorJobsData,
} from "../types";

const api = axios.create({ baseURL: "/api" });

/** Filters shared by the summary, timeseries (chart + daily table) endpoints. */
export interface MetricFilters {
  campaign?: string;
  asin?: string;
  status?: string;        // "" | "Enabled" | "Paused" | "Removed"
  country_code?: string;  // "" | "US" | "UK" | ...
  campaign_type?: string; // "" | "brand" | "amazon"
  age_min?: number | null;
  age_max?: number | null;
}

/** Build axios params from filters; undefined values are omitted by axios. */
function filterParams(f?: MetricFilters): Record<string, string | number | undefined> {
  if (!f) return {};
  return {
    campaign: f.campaign || "",
    asin: f.asin || "",
    status: f.status || "",
    country_code: f.country_code || "",
    campaign_type: f.campaign_type || "",
    age_min: f.age_min ?? undefined,
    age_max: f.age_max ?? undefined,
  };
}

export async function fetchSummary(
  dateFrom: string,
  dateTo: string,
  filters?: MetricFilters
): Promise<SummaryData> {
  const { data } = await api.get("/dashboard/summary", {
    params: { date_from: dateFrom, date_to: dateTo, ...filterParams(filters) },
  });
  return data;
}

export async function fetchCampaigns(
  dateFrom: string,
  dateTo: string,
  sortBy = "spend_usd",
  sortDir = "desc",
  asin = "",
  campaign = "",
  status = "",
  countryCode = "",
  campaignType = ""
): Promise<CampaignsData> {
  const { data } = await api.get("/dashboard/campaigns", {
    params: {
      date_from: dateFrom,
      date_to: dateTo,
      sort_by: sortBy,
      sort_dir: sortDir,
      asin,
      campaign,
      status,
      country_code: countryCode,
      campaign_type: campaignType,
    },
  });
  return data;
}

export async function fetchCampaignDates(
  campaignId: string,
  dateFrom: string,
  dateTo: string,
  groupby: GroupBy = "day"
): Promise<CampaignDatesData> {
  const { data } = await api.get(`/dashboard/campaigns/${campaignId}/dates`, {
    params: { date_from: dateFrom, date_to: dateTo, groupby },
  });
  return data;
}

export async function fetchTimeseries(
  dateFrom: string,
  dateTo: string,
  groupby: GroupBy,
  filters?: MetricFilters
): Promise<TimeseriesData> {
  const { data } = await api.get("/dashboard/timeseries", {
    params: { date_from: dateFrom, date_to: dateTo, groupby, ...filterParams(filters) },
  });
  return data;
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const { data } = await api.get("/sync/status");
  return data;
}

export async function triggerSync(): Promise<void> {
  await api.post("/sync/trigger");
}

export async function fetchDetailedExport(
  dateFrom: string,
  dateTo: string,
  groupby: GroupBy
): Promise<DetailedExportRow[]> {
  const { data } = await api.get("/dashboard/export/detailed", {
    params: { date_from: dateFrom, date_to: dateTo, groupby },
  });
  return data.rows;
}

export async function uploadTestBatch(file: File): Promise<TestBatchUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/testing/batch", form);
  return data;
}

export async function fetchTestStatus(): Promise<TestStatusData> {
  const { data } = await api.get("/testing/status");
  return data;
}

export function testingExportUrl(): string {
  return "/api/testing/export";
}

export async function markActionApplied(
  campaignId: number,
  action: "cut" | "scale_bid" | "mature_bid"
): Promise<void> {
  await api.post(`/testing/campaigns/${campaignId}/mark-applied`, { action });
}

export async function resetAppliedAction(campaignId: number): Promise<void> {
  await api.post(`/testing/campaigns/${campaignId}/reset`);
}

// ── Catalog ───────────────────────────────────────────────────────────────────

export async function fetchCatalogProducts(
  countryCode = "",
  search = "",
  page = 1
): Promise<ProductCatalogData> {
  const { data } = await api.get("/catalog/products", {
    params: { country_code: countryCode, search, page },
  });
  return data;
}

export async function triggerCatalogSync(): Promise<void> {
  await api.post("/catalog/sync");
}

export async function fetchCatalogSyncStatus(): Promise<CatalogSyncStatus[]> {
  const { data } = await api.get("/catalog/sync/status");
  return data.markets;
}

// ── Campaign Drafts ───────────────────────────────────────────────────────────

export async function generateCampaignDrafts(
  items: { asin: string; country_code: string }[]
): Promise<CampaignDraft[]> {
  const { data } = await api.post("/campaigns/drafts", { items });
  return data.drafts;
}

export async function fetchCampaignDrafts(
  countryCode = "",
  status = ""
): Promise<CampaignDraftsData> {
  const { data } = await api.get("/campaigns/drafts", {
    params: { country_code: countryCode, status },
  });
  return data;
}

export async function markDraftExported(draftId: number): Promise<void> {
  await api.post(`/campaigns/drafts/${draftId}/mark-exported`);
}

export function campaignExportUrl(): string {
  return "/api/campaigns/export";
}

// ── Campaign Creator ──────────────────────────────────────────────────────────

export async function startCampaignJob(
  items: Array<{ asin: string; product_name: string | null }>,
  campaignType: "brand" | "amazon" = "brand"
): Promise<{ job_id: string; total: number }> {
  const { data } = await api.post("/campaign-creator/start", { items, campaign_type: campaignType });
  return data;
}

export async function getCampaignJobStatus(
  jobId: string
): Promise<CampaignCreatorJob> {
  const { data } = await api.get(`/campaign-creator/jobs/${jobId}`);
  return data;
}

export async function listCampaignJobs(): Promise<CampaignCreatorJob[]> {
  const { data }: { data: CampaignCreatorJobsData } = await api.get(
    "/campaign-creator/jobs"
  );
  return data.jobs;
}

export function campaignCreatorDownloadUrl(jobId: string): string {
  return `/api/campaign-creator/jobs/${jobId}/download`;
}

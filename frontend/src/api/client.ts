import axios from "axios";
import type {
  SummaryData,
  CampaignsData,
  CampaignDatesData,
  TimeseriesData,
  SyncStatus,
  GroupBy,
} from "../types";

const api = axios.create({ baseURL: "/api" });

export async function fetchSummary(
  dateFrom: string,
  dateTo: string
): Promise<SummaryData> {
  const { data } = await api.get("/dashboard/summary", {
    params: { date_from: dateFrom, date_to: dateTo },
  });
  return data;
}

export async function fetchCampaigns(
  dateFrom: string,
  dateTo: string,
  sortBy = "spend_usd",
  sortDir = "desc",
  asin = "",
  campaign = ""
): Promise<CampaignsData> {
  const { data } = await api.get("/dashboard/campaigns", {
    params: {
      date_from: dateFrom,
      date_to: dateTo,
      sort_by: sortBy,
      sort_dir: sortDir,
      asin,
      campaign,
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
  groupby: GroupBy
): Promise<TimeseriesData> {
  const { data } = await api.get("/dashboard/timeseries", {
    params: { date_from: dateFrom, date_to: dateTo, groupby },
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

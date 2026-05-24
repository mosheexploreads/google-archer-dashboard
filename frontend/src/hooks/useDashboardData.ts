import { useState, useEffect, useCallback } from "react";
import {
  fetchSummary,
  fetchCampaigns,
  fetchTimeseries,
} from "../api/client";
import type {
  SummaryData,
  CampaignsData,
  TimeseriesData,
} from "../types";

interface DashboardState {
  summary: SummaryData | null;
  campaigns: CampaignsData | null;
  timeseries: TimeseriesData | null;
  loading: boolean;
  error: string | null;
}

export function useDashboardData(dateFrom: string, dateTo: string, countryCode = "") {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    campaigns: null,
    timeseries: null,
    loading: false,
    error: null,
  });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const [summary, campaigns, timeseries] = await Promise.all([
        fetchSummary(dateFrom, dateTo, countryCode),
        fetchCampaigns(dateFrom, dateTo, "spend_usd", "desc", "", "", "", countryCode),
        fetchTimeseries(dateFrom, dateTo, "day"),
      ]);
      setState({ summary, campaigns, timeseries, loading: false, error: null });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setState((s) => ({ ...s, loading: false, error: msg }));
    }
  }, [dateFrom, dateTo, countryCode]);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}

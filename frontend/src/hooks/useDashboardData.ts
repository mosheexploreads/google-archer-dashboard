import { useState, useEffect, useCallback } from "react";
import {
  fetchSummary,
  fetchCampaigns,
  fetchTimeseries,
} from "../api/client";
import type { MetricFilters } from "../api/client";
import type {
  SummaryData,
  CampaignsData,
  TimeseriesData,
} from "../types";

interface DashboardState {
  summary: SummaryData | null;
  campaigns: CampaignsData | null;
  timeseries: TimeseriesData | null;
  loading: boolean;        // campaign table data (date-driven)
  metricsLoading: boolean; // summary cards + chart + daily table (filter-driven)
  error: string | null;
}

const EMPTY_FILTERS: MetricFilters = {};

export function useDashboardData(
  dateFrom: string,
  dateTo: string,
  filters: MetricFilters = EMPTY_FILTERS
) {
  const [state, setState] = useState<DashboardState>({
    summary: null,
    campaigns: null,
    timeseries: null,
    loading: false,
    metricsLoading: false,
    error: null,
  });

  // Campaign table holds the full set and filters it client-side, so this only
  // depends on the date range — filter changes never reload or blank the table.
  const loadCampaigns = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const campaigns = await fetchCampaigns(dateFrom, dateTo);
      setState((s) => ({ ...s, campaigns, loading: false }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setState((s) => ({ ...s, loading: false, error: msg }));
    }
  }, [dateFrom, dateTo]);

  // Summary + timeseries reflect the active filters (server-side), so the cards,
  // chart, and daily breakdown all show the same filtered campaign subset.
  const loadMetrics = useCallback(async () => {
    setState((s) => ({ ...s, metricsLoading: true, error: null }));
    try {
      const [summary, timeseries] = await Promise.all([
        fetchSummary(dateFrom, dateTo, filters),
        fetchTimeseries(dateFrom, dateTo, "day", filters),
      ]);
      setState((s) => ({ ...s, summary, timeseries, metricsLoading: false }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setState((s) => ({ ...s, metricsLoading: false, error: msg }));
    }
  }, [dateFrom, dateTo, filters]);

  useEffect(() => { loadCampaigns(); }, [loadCampaigns]);
  useEffect(() => { loadMetrics(); }, [loadMetrics]);

  const reload = useCallback(() => {
    loadCampaigns();
    loadMetrics();
  }, [loadCampaigns, loadMetrics]);

  return { ...state, reload };
}

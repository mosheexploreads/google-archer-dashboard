import { useState, useEffect, useRef, useMemo } from "react";
import { AppShell } from "./components/layout/AppShell";
import { DateRangeSelector } from "./components/controls/DateRangeSelector";
import { GroupingToggle } from "./components/controls/GroupingToggle";
import { SummaryCards } from "./components/cards/SummaryCards";
import { SpendRevenueChart } from "./components/charts/SpendRevenueChart";
import { CampaignTable } from "./components/table/CampaignTable";
import { DateBreakdownTable } from "./components/table/DateBreakdownTable";
import { ExportModal } from "./components/export/ExportModal";
import { CsvUpload } from "./components/shared/CsvUpload";
import { WarningBanner } from "./components/shared/WarningBanner";
import { TestingPage } from "./components/testing/TestingPage";
import { CatalogPage } from "./components/catalog/CatalogPage";
import { CampaignsPage } from "./components/campaigns/CampaignsPage";
import { CreateCampaignsPage } from "./components/campaigns/CreateCampaignsPage";
import { DiscoveryPage } from "./components/discovery/DiscoveryPage";
import { useDashboardData } from "./hooks/useDashboardData";
import { useDebounce } from "./hooks/useDebounce";
import { useRefresh } from "./hooks/useRefresh";
import { useWarnings } from "./hooks/useWarnings";
import { EMPTY_DASHBOARD_FILTERS } from "./components/table/TableFilters";
import type { DashboardFilters } from "./components/table/TableFilters";
import type { MetricFilters } from "./api/client";
import type { DateRange, GroupBy, DateRow, CampaignRow } from "./types";

type Tab = "dashboard" | "testing" | "catalog" | "campaigns" | "create" | "discover";

const TAB_LABELS: Record<Tab, string> = {
  dashboard: "Dashboard",
  testing: "Testing",
  catalog: "Product Catalog",
  campaigns: "Campaigns",
  create: "Create Campaigns",
  discover: "Discover",
};

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [dateRange, setDateRange] = useState<DateRange>({
    from: daysAgo(7),
    to: daysAgo(1),
  });
  const [groupby, setGroupby] = useState<GroupBy>("day");
  const [showExport, setShowExport] = useState(false);
  const [exportRows, setExportRows] = useState<CampaignRow[]>([]);

  // Filter state lives here so the campaign table AND the summary/chart/daily
  // table all reflect the same filtered campaign subset.
  const [filters, setFilters] = useState<DashboardFilters>(EMPTY_DASHBOARD_FILTERS);

  // Convert UI filter state → API params. "All" / "" mean "no filter".
  const metricFilters = useMemo<MetricFilters>(() => ({
    campaign: filters.campaign,
    asin: filters.asin,
    status: filters.status === "All" ? "" : filters.status,
    country_code: filters.country === "All" ? "" : filters.country,
    campaign_type: filters.type === "All" ? "" : filters.type.toLowerCase(),
    age_min: filters.ageMin === "" ? null : filters.ageMin,
    age_max: filters.ageMax === "" ? null : filters.ageMax,
    account: filters.account === "All" ? "" : filters.account,
  }), [filters]);

  // Debounce so typing in the text filters doesn't refetch on every keystroke.
  const debouncedFilters = useDebounce(metricFilters, 300);

  // Shared cache for date drill-down data — populated by DateDrillDown on expand
  const dateDataRef = useRef<Record<string, DateRow[]>>({});

  const { summary, campaigns, timeseries, loading, metricsLoading, error, reload } =
    useDashboardData(dateRange.from, dateRange.to, debouncedFilters);

  const { syncStatus, loadStatus, handleTrigger, triggering } = useRefresh(reload);
  const { warnings, reload: reloadWarnings } = useWarnings();

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  // Reset date cache when date range changes (stale data)
  useEffect(() => {
    dateDataRef.current = {};
  }, [dateRange, groupby]);

  return (
    <AppShell syncStatus={syncStatus} onRefresh={handleTrigger} refreshing={triggering}>
      {/* Tab navigation */}
      <div className="flex gap-1 border-b border-gray-200 -mb-2">
        {(["dashboard", "testing", "create", "discover"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t transition-colors ${
              tab === t
                ? "text-blue-600 border-b-2 border-blue-600 bg-white"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === "testing" && <TestingPage />}
      {tab === "create" && <CreateCampaignsPage />}
      {tab === "catalog" && <CatalogPage />}
      {tab === "campaigns" && <CampaignsPage />}
      {tab === "discover" && <DiscoveryPage />}

      {tab === "dashboard" && <>
      {/* Controls row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <DateRangeSelector value={dateRange} onChange={setDateRange} />
        <GroupingToggle value={groupby} onChange={setGroupby} />
      </div>

      {/* Archer removal warnings */}
      <WarningBanner warnings={warnings} />

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          Error loading data: {error}
        </div>
      )}

      {/* Summary cards */}
      <SummaryCards data={summary} loading={metricsLoading} />

      {/* Timeseries chart */}
      <SpendRevenueChart data={timeseries?.points ?? []} loading={metricsLoading} />

      {/* Date breakdown table */}
      <DateBreakdownTable points={timeseries?.points ?? []} loading={metricsLoading} />

      {/* CSV upload */}
      <CsvUpload onSuccess={() => { reload(); reloadWarnings(); }} />

      {/* Two-level expandable campaign table */}
      <CampaignTable
        rows={campaigns?.rows ?? []}
        loading={loading}
        dateRange={dateRange}
        groupby={groupby}
        onExport={(filteredRows) => { setExportRows(filteredRows); setShowExport(true); }}
        dateDataRef={dateDataRef}
        filters={filters}
        onFiltersChange={setFilters}
      />

      {/* CSV Export modal */}
      {showExport && (
        <ExportModal
          campaigns={exportRows}
          dateRange={dateRange}
          groupby={groupby}
          onClose={() => setShowExport(false)}
        />
      )}
      </>}
    </AppShell>
  );
}

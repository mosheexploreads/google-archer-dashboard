import { useState, useEffect, useRef } from "react";
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
import { useDashboardData } from "./hooks/useDashboardData";
import { useRefresh } from "./hooks/useRefresh";
import { useWarnings } from "./hooks/useWarnings";
import type { DateRange, GroupBy, DateRow, CampaignRow } from "./types";

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function App() {
  const [dateRange, setDateRange] = useState<DateRange>({
    from: daysAgo(7),
    to: daysAgo(1),
  });
  const [groupby, setGroupby] = useState<GroupBy>("day");
  const [showExport, setShowExport] = useState(false);
  const [exportRows, setExportRows] = useState<CampaignRow[]>([]);

  // Shared cache for date drill-down data — populated by DateDrillDown on expand
  const dateDataRef = useRef<Record<string, DateRow[]>>({});

  const { summary, campaigns, timeseries, loading, error, reload } =
    useDashboardData(dateRange.from, dateRange.to);

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
      <SummaryCards data={summary} loading={loading} />

      {/* Timeseries chart */}
      <SpendRevenueChart data={timeseries?.points ?? []} loading={loading} />

      {/* Date breakdown table */}
      <DateBreakdownTable points={timeseries?.points ?? []} loading={loading} />

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
      />

      {/* CSV Export modal */}
      {showExport && (
        <ExportModal
          campaigns={exportRows}
          dateData={dateDataRef.current}
          dateRange={dateRange}
          onClose={() => setShowExport(false)}
        />
      )}
    </AppShell>
  );
}

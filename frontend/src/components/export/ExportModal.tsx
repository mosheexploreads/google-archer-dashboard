import { useState } from "react";
import { exportAggregated, exportDetailed } from "../../utils/csvExport";
import { fetchDetailedExport } from "../../api/client";
import type { CampaignRow, DateRange, GroupBy, RevenueSource } from "../../types";

type Format = "aggregated" | "detailed";

interface Props {
  campaigns: CampaignRow[];
  dateRange: DateRange;
  groupby: GroupBy;
  revenueSource?: RevenueSource;
  onClose: () => void;
}

export function ExportModal({ campaigns, dateRange, groupby, revenueSource = "auto", onClose }: Props) {
  const [format, setFormat] = useState<Format>("aggregated");
  const [loading, setLoading] = useState(false);

  async function handleDownload() {
    if (format === "aggregated") {
      exportAggregated(campaigns, dateRange);
      onClose();
    } else {
      setLoading(true);
      try {
        const rows = await fetchDetailedExport(dateRange.from, dateRange.to, groupby, revenueSource);
        exportDetailed(rows, dateRange);
        onClose();
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-80 p-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">Export to CSV</h2>

        <div className="space-y-3">
          {/* Aggregated option */}
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="radio"
              name="format"
              value="aggregated"
              checked={format === "aggregated"}
              onChange={() => setFormat("aggregated")}
              className="mt-0.5 accent-blue-600"
            />
            <div>
              <div className="text-sm font-medium text-gray-800">Aggregated (by campaign)</div>
              <div className="text-xs text-gray-500 mt-0.5">
                One row per campaign, totals across selected dates
              </div>
            </div>
          </label>

          {/* Detailed option */}
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="radio"
              name="format"
              value="detailed"
              checked={format === "detailed"}
              onChange={() => setFormat("detailed")}
              className="mt-0.5 accent-blue-600"
            />
            <div>
              <div className="text-sm font-medium text-gray-800">Detailed (campaign × date)</div>
              <div className="text-xs text-gray-500 mt-0.5">
                All campaigns broken down by {groupby} for the selected date range
              </div>
            </div>
          </label>
        </div>

        <div className="flex gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={loading}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleDownload}
            disabled={loading}
            className="flex-1 px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Fetching…" : "Download"}
          </button>
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect, useCallback } from "react";
import { fetchTestStatus, testingExportUrl } from "../../api/client";
import type { TestStatusData, TestBatchUploadResult } from "../../types";
import { TestBatchUpload } from "./TestBatchUpload";
import { TestingTable } from "./TestingTable";

export function TestingPage() {
  const [data, setData] = useState<TestStatusData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchTestStatus();
      setData(res);
    } catch {
      setError("Failed to load test status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function onUploadSuccess(_result: TestBatchUploadResult) {
    load();
  }

  const needsAction = data?.needs_action ?? 0;
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Campaign Testing</h1>
          {total > 0 && (
            <p className="mt-0.5 text-sm text-gray-500">
              {total} campaigns tracked — {needsAction} need action
            </p>
          )}
        </div>
        {total > 0 && (
          <a
            href={testingExportUrl()}
            download="google_ads_actions.csv"
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              needsAction > 0
                ? "bg-blue-600 text-white hover:bg-blue-700"
                : "bg-gray-100 text-gray-500 cursor-default pointer-events-none"
            }`}
          >
            Export Google Ads Editor CSV
            {needsAction > 0 && (
              <span className="ml-1 bg-white text-blue-700 rounded-full px-1.5 py-0.5 text-xs font-bold">
                {needsAction}
              </span>
            )}
          </a>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* How it works info box */}
      <div className="rounded-xl border border-blue-100 bg-blue-50 px-5 py-4 text-sm text-blue-900 space-y-1">
        <p className="font-medium">How testing rules work</p>
        <ul className="list-disc list-inside space-y-0.5 text-blue-800">
          <li>AOV &lt; $10 → cut after 30 clicks with no sale</li>
          <li>AOV $10–$20 → cut after 60 clicks with no sale</li>
          <li>AOV &gt; $20 → cut after 100 clicks with no sale</li>
          <li>At 100 clicks with ≥1 sale: cut if RPC &lt; CPC, else confirm winner</li>
          <li>Winner bids: RPC × 0.70 (scaling) → RPC × 0.85 at 200+ clicks (mature)</li>
        </ul>
      </div>

      <TestBatchUpload onSuccess={onUploadSuccess} />

      <TestingTable
        campaigns={data?.campaigns ?? []}
        loading={loading && !data}
      />
    </div>
  );
}

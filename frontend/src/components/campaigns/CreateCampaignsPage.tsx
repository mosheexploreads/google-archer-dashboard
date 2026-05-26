import { useState, useEffect, useRef, useCallback } from "react";
import type { CampaignCreatorJob } from "../../types";
import {
  startCampaignJob,
  getCampaignJobStatus,
  listCampaignJobs,
  campaignCreatorDownloadUrl,
} from "../../api/client";

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseInput(
  text: string
): Array<{ asin: string; product_name: string | null }> {
  return text
    .trim()
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
    .map((line) => {
      const parts = line.split("\t");
      return {
        asin: parts[0].trim().toUpperCase(),
        product_name: parts[1]?.trim() || null,
      };
    })
    .filter((item) => /^[A-Z0-9]{10}$/.test(item.asin));
}

function statusBadge(status: CampaignCreatorJob["status"]): string {
  switch (status) {
    case "completed":
      return "bg-green-100 text-green-700";
    case "partial":
      return "bg-amber-100 text-amber-700";
    case "failed":
      return "bg-red-100 text-red-700";
    case "running":
      return "bg-blue-100 text-blue-700";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CreateCampaignsPage() {
  const [input, setInput] = useState("");
  const [campaignType, setCampaignType] = useState<"brand" | "amazon">("brand");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<CampaignCreatorJob | null>(null);
  const [jobs, setJobs] = useState<CampaignCreatorJob[]>([]);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load recent jobs on mount
  useEffect(() => {
    listCampaignJobs()
      .then(setJobs)
      .catch(() => {});
  }, []);

  // Update a job in the list (or prepend if new)
  const updateJobInList = useCallback((job: CampaignCreatorJob) => {
    setJobs((prev) => {
      const idx = prev.findIndex((j) => j.job_id === job.job_id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = job;
        return next;
      }
      return [job, ...prev];
    });
  }, []);

  // Poll active job every 3 s while it's running/pending
  useEffect(() => {
    if (!activeJobId) return;

    const poll = async () => {
      try {
        const status = await getCampaignJobStatus(activeJobId);
        setActiveJob(status);
        updateJobInList(status);
        if (["completed", "failed", "partial"].includes(status.status)) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
        }
      } catch {
        // non-fatal
      }
    };

    poll(); // immediate first check
    pollRef.current = setInterval(poll, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [activeJobId, updateJobInList]);

  const parsedItems = parseInput(input);

  async function handleStart() {
    if (parsedItems.length === 0) {
      setError(
        "No valid ASINs found. Each line should be an ASIN (10 alphanumeric chars), " +
          "optionally followed by a tab and the product name."
      );
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const { job_id } = await startCampaignJob(parsedItems, campaignType);
      setActiveJobId(job_id);
      setActiveJob(null);
      setInput("");
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Failed to start job";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  const progressPct =
    activeJob && activeJob.total > 0
      ? Math.round((activeJob.processed / activeJob.total) * 100)
      : 0;

  const isDone =
    activeJob &&
    ["completed", "partial", "failed"].includes(activeJob.status);

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900">
          Create Campaigns
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Paste one ASIN per line. Optionally add a tab + product name to skip
          the Archer lookup. Claude generates ad copy; you download a
          ready-to-import Google Ads Editor ZIP.
        </p>
      </div>

      {/* Input area */}
      <div className="space-y-3">
        <textarea
          className="w-full h-48 font-mono text-sm border border-gray-300 rounded-lg p-3
                     focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
          placeholder={
            "B0DTQ34CJH\tFull Product Name Here\nB0CL6C7X55\nB0ABC123DE\t..."
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={submitting}
        />

        {/* Campaign type selector */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600 font-medium">Campaign type:</span>
          <div className="flex rounded-md border border-gray-300 overflow-hidden text-sm font-medium">
            <button
              onClick={() => setCampaignType("brand")}
              className={`px-4 py-1.5 transition-colors ${
                campaignType === "brand"
                  ? "bg-purple-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              [Brand] — Branded keywords
            </button>
            <button
              onClick={() => setCampaignType("amazon")}
              className={`px-4 py-1.5 border-l border-gray-300 transition-colors ${
                campaignType === "amazon"
                  ? "bg-orange-500 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              [Amazon] — Category + Amazon keywords
            </button>
          </div>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex items-center gap-4">
          <button
            onClick={handleStart}
            disabled={submitting || parsedItems.length === 0}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Starting…" : "Generate Campaigns"}
          </button>
          {parsedItems.length > 0 && (
            <span className="text-sm text-gray-500">
              {parsedItems.length} ASIN{parsedItems.length !== 1 ? "s" : ""}{" "}
              detected
              {parsedItems.filter((i) => i.product_name).length > 0 &&
                ` (${parsedItems.filter((i) => i.product_name).length} with name)`}
            </span>
          )}
        </div>
      </div>

      {/* Active job progress */}
      {activeJob && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="text-sm font-medium text-gray-900">
                Job {activeJob.job_id.slice(0, 8)}…
              </span>
              <span
                className={`ml-2 text-xs font-medium px-1.5 py-0.5 rounded-full ${statusBadge(
                  activeJob.status
                )}`}
              >
                {activeJob.status}
              </span>
              <span className={`ml-1.5 text-xs font-medium px-1.5 py-0.5 rounded-full ${
                activeJob.campaign_type === "amazon"
                  ? "bg-orange-100 text-orange-700"
                  : "bg-purple-100 text-purple-700"
              }`}>
                {activeJob.campaign_type === "amazon" ? "Amazon" : "Brand"}
              </span>
            </div>
            {(activeJob.status === "completed" ||
              activeJob.status === "partial") && (
              <a
                href={campaignCreatorDownloadUrl(activeJob.job_id)}
                className="px-3 py-1.5 bg-green-600 text-white text-sm font-medium
                           rounded-lg hover:bg-green-700 flex-shrink-0"
                download
              >
                ⬇ Download ZIP
              </a>
            )}
          </div>

          {/* Progress bar */}
          <div>
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>
                {activeJob.processed} / {activeJob.total} processed
                {activeJob.failed_count > 0 && (
                  <span className="text-amber-600 ml-2">
                    ({activeJob.failed_count} failed)
                  </span>
                )}
              </span>
              <span>{progressPct}%</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${
                  isDone && activeJob.status === "failed"
                    ? "bg-red-500"
                    : isDone && activeJob.status === "partial"
                    ? "bg-amber-500"
                    : "bg-blue-500"
                }`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {!isDone && (
            <p className="text-xs text-gray-400">
              Processing — this page polls automatically every 3 seconds.
            </p>
          )}
        </div>
      )}

      {/* Recent jobs list */}
      {jobs.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Recent Jobs
          </h3>
          <div className="space-y-1.5">
            {jobs.slice(0, 15).map((job) => (
              <div
                key={job.job_id}
                className="flex items-center justify-between bg-gray-50 border
                           border-gray-200 rounded-lg px-3 py-2 gap-3"
              >
                <div className="min-w-0 flex items-center gap-2 text-sm">
                  <span className="font-mono text-gray-600 flex-shrink-0">
                    {job.job_id.slice(0, 8)}…
                  </span>
                  <span
                    className={`text-xs font-medium px-1.5 py-0.5 rounded-full flex-shrink-0 ${statusBadge(
                      job.status
                    )}`}
                  >
                    {job.status}
                  </span>
                  <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                    job.campaign_type === "amazon"
                      ? "bg-orange-100 text-orange-700"
                      : "bg-purple-100 text-purple-700"
                  }`}>
                    {job.campaign_type === "amazon" ? "Amazon" : "Brand"}
                  </span>
                  <span className="text-gray-500 text-xs">
                    {job.processed}/{job.total}
                    {job.failed_count > 0 && (
                      <span className="text-amber-600">
                        {" "}
                        ({job.failed_count} failed)
                      </span>
                    )}
                  </span>
                  <span className="text-gray-400 text-xs hidden sm:inline">
                    {formatDate(job.created_at)}
                  </span>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {(job.status === "completed" || job.status === "partial") && (
                    <a
                      href={campaignCreatorDownloadUrl(job.job_id)}
                      className="text-sm text-blue-600 hover:underline"
                      download
                    >
                      Download
                    </a>
                  )}
                  {(job.status === "pending" || job.status === "running") &&
                    job.job_id !== activeJobId && (
                      <button
                        onClick={() => setActiveJobId(job.job_id)}
                        className="text-sm text-blue-600 hover:underline"
                      >
                        Watch
                      </button>
                    )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

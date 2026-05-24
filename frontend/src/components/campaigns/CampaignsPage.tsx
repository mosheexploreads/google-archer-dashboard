import { useState, useEffect, useCallback } from "react";
import { fetchCampaignDrafts, markDraftExported, campaignExportUrl } from "../../api/client";
import type { CampaignDraft } from "../../types";

const COUNTRY_OPTIONS = ["All", "UK", "DE", "JP", "CA"] as const;
type CountryOption = (typeof COUNTRY_OPTIONS)[number];

const STATUS_OPTIONS = ["All", "draft", "exported"] as const;
type StatusOption = (typeof STATUS_OPTIONS)[number];

export function CampaignsPage() {
  const [drafts, setDrafts] = useState<CampaignDraft[]>([]);
  const [total, setTotal] = useState(0);
  const [countryFilter, setCountryFilter] = useState<CountryOption>("All");
  const [statusFilter, setStatusFilter] = useState<StatusOption>("All");
  const [loading, setLoading] = useState(false);
  const [marking, setMarking] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const cc = countryFilter === "All" ? "" : countryFilter;
      const st = statusFilter === "All" ? "" : statusFilter;
      const result = await fetchCampaignDrafts(cc, st);
      setDrafts(result.drafts);
      setTotal(result.total);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [countryFilter, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleMarkExported = async (id: number) => {
    setMarking(id);
    try {
      await markDraftExported(id);
      await load();
    } catch {
      // silent
    } finally {
      setMarking(null);
    }
  };

  const draftCount = drafts.filter((d) => d.status === "draft").length;

  const thBase = "px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const tdBase = "px-3 py-2 text-xs text-gray-800";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Campaign Drafts</h2>
          <p className="text-xs text-gray-500 mt-0.5">{total} total · {draftCount} ready to export</p>
        </div>
        <a
          href={campaignExportUrl()}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            draftCount > 0
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "border border-gray-300 bg-white text-gray-400 cursor-not-allowed pointer-events-none"
          }`}
        >
          ↓ Export Google Ads CSV ({draftCount})
        </a>
      </div>

      {/* Info box */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg px-4 py-3 text-xs text-gray-600 space-y-1">
        <p><strong>How it works:</strong> Select products in the Product Catalog tab → click "Create Campaigns" → attribution links are generated automatically.</p>
        <p>Download the CSV above and import it into Google Ads Editor. Each campaign name follows <code className="bg-gray-100 px-1 rounded">Product Name - ASIN - COUNTRY</code> convention.</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex rounded-md border border-gray-300 overflow-hidden text-xs font-medium">
          {COUNTRY_OPTIONS.map((opt) => (
            <button
              key={opt}
              onClick={() => setCountryFilter(opt)}
              className={`px-3 py-1.5 transition-colors ${
                countryFilter === opt ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
              } ${opt !== "All" ? "border-l border-gray-300" : ""}`}
            >
              {opt}
            </button>
          ))}
        </div>
        <div className="flex rounded-md border border-gray-300 overflow-hidden text-xs font-medium">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt}
              onClick={() => setStatusFilter(opt)}
              className={`px-3 py-1.5 capitalize transition-colors ${
                statusFilter === opt ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
              } ${opt !== "All" ? "border-l border-gray-300" : ""}`}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-x-auto">
        {loading ? (
          <div className="h-48 animate-pulse bg-gray-50" />
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className={thBase}>Campaign Name</th>
                <th className={thBase}>ASIN</th>
                <th className={`${thBase} text-center`}>Market</th>
                <th className={thBase}>Attribution Link</th>
                <th className={`${thBase} text-right`}>Bid</th>
                <th className={`${thBase} text-center`}>Status</th>
                <th className={thBase}>Created</th>
                <th className={thBase} />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {drafts.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-400 text-sm">
                    No campaign drafts yet. Go to Product Catalog, select products, and click "Create Campaigns".
                  </td>
                </tr>
              )}
              {drafts.map((d) => (
                <tr key={d.id} className="hover:bg-gray-50 transition-colors">
                  <td className={`${tdBase} font-medium`} style={{ maxWidth: 260 }}>
                    <span className="truncate block" title={d.campaign_name}>{d.campaign_name}</span>
                    {d.product_name && (
                      <span className="text-gray-400 text-[10px]">{d.product_name}</span>
                    )}
                  </td>
                  <td className={`${tdBase} font-mono text-gray-500`}>{d.asin}</td>
                  <td className={`${tdBase} text-center`}>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-600">
                      {d.country_code}
                    </span>
                  </td>
                  <td className={tdBase} style={{ maxWidth: 200 }}>
                    {d.attribution_link ? (
                      <a
                        href={d.attribution_link}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline truncate block"
                        title={d.attribution_link}
                      >
                        {d.attribution_link}
                      </a>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className={`${tdBase} text-right`}>${d.suggested_bid.toFixed(2)}</td>
                  <td className={`${tdBase} text-center`}>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      d.status === "draft"
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-green-100 text-green-700"
                    }`}>
                      {d.status}
                    </span>
                  </td>
                  <td className={`${tdBase} text-gray-400`}>
                    {d.created_at ? new Date(d.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td className={tdBase}>
                    {d.status === "draft" && (
                      <button
                        onClick={() => handleMarkExported(d.id)}
                        disabled={marking === d.id}
                        className="text-xs text-gray-500 hover:text-gray-700 disabled:opacity-50"
                      >
                        {marking === d.id ? "..." : "Mark exported"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="text-xs text-gray-400">{drafts.length} drafts shown</div>
    </div>
  );
}

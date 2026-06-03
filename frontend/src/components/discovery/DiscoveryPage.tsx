import { useState, useEffect, useRef } from "react";

const API = "";

interface ScanStatus {
  id: number;
  status: "running" | "complete" | "error";
  min_rating: number;
  min_reviews: number;
  max_rank: number;
  total_archer: number;
  total_filtered: number;
  total_ranked: number;
  total_found: number;
  started_at: string;
  finished_at: string | null;
  error: string | null;
  progress_pct: number;
}

interface Product {
  id: number;
  asin: string;
  product_name: string | null;
  rating: number | null;
  review_count: number | null;
  price: number | null;
  image_url: string | null;
  subcategory: string | null;
  rank: number | null;
  has_campaign: boolean;
}

interface Results {
  scan_id: number;
  total: number;
  new_only: number;
  products: Product[];
}

function StarRating({ rating }: { rating: number | null }) {
  if (rating == null) return <span className="text-gray-400">—</span>;
  const full = Math.floor(rating);
  return (
    <span className="text-yellow-500 font-medium">
      {"★".repeat(full)}{"☆".repeat(5 - full)} {rating.toFixed(1)}
    </span>
  );
}

export function DiscoveryPage() {
  const [minRating, setMinRating] = useState(4.2);
  const [minReviews, setMinReviews] = useState(100);
  const [maxRank, setMaxRank] = useState(5);
  const [hideExisting, setHideExisting] = useState(false);
  const [scan, setScan] = useState<ScanStatus | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load latest scan on mount
  useEffect(() => {
    fetchLatestScan();
    return () => stopPolling();
  }, []);

  // Auto-load results when scan completes
  useEffect(() => {
    if (scan?.status === "complete") {
      stopPolling();
      fetchResults();
    } else if (scan?.status === "error") {
      stopPolling();
    }
  }, [scan?.status, scan?.id]);

  // Re-fetch results when hideExisting changes
  useEffect(() => {
    if (scan?.status === "complete") fetchResults();
  }, [hideExisting]);

  async function fetchLatestScan() {
    try {
      const r = await fetch(`${API}/api/discovery/scan/latest`);
      if (r.ok) {
        const data = await r.json();
        setScan(data);
        if (data?.status === "running") startPolling();
        if (data?.status === "complete") fetchResults();
      }
    } catch {
      // no scan yet
    }
  }

  async function fetchResults() {
    try {
      const r = await fetch(`${API}/api/discovery/results?hide_existing=${hideExisting}`);
      if (r.ok) setResults(await r.json());
    } catch (e) {
      console.error("Failed to fetch results", e);
    }
  }

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const r = await fetch(`${API}/api/discovery/scan/latest`);
      if (r.ok) {
        const data = await r.json();
        setScan(data);
      }
    }, 2000);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function startScan() {
    setError(null);
    setResults(null);
    setSelected(new Set());
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/discovery/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ min_rating: minRating, min_reviews: minReviews, max_rank: maxRank }),
      });
      if (!r.ok) {
        const d = await r.json();
        throw new Error(d.detail || "Failed to start scan");
      }
      const data = await r.json();
      setScan(data);
      startPolling();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function toggleSelect(asin: string) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(asin) ? next.delete(asin) : next.add(asin);
      return next;
    });
  }

  function toggleAll() {
    if (!results) return;
    if (selected.size === results.products.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(results.products.map(p => p.asin)));
    }
  }

  function copySelected() {
    const text = Array.from(selected).join("\n");
    navigator.clipboard.writeText(text);
  }

  const isRunning = scan?.status === "running";
  const displayProducts = results?.products ?? [];

  return (
    <div className="space-y-6 p-4">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-800">Product Discovery</h2>
        <p className="text-sm text-gray-500 mt-1">
          Scan Archer's catalog, filter by quality, then find products ranked top {maxRank} in their Amazon subcategory.
        </p>
      </div>

      {/* Settings card */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Scan Settings</h3>
        <div className="flex flex-wrap gap-6 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Min. Rating</label>
            <input
              type="number"
              step="0.1"
              min="1"
              max="5"
              value={minRating}
              onChange={e => setMinRating(parseFloat(e.target.value))}
              disabled={isRunning}
              className="w-24 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Min. Reviews</label>
            <input
              type="number"
              step="10"
              min="0"
              value={minReviews}
              onChange={e => setMinReviews(parseInt(e.target.value))}
              disabled={isRunning}
              className="w-28 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Top N in Subcategory</label>
            <input
              type="number"
              step="1"
              min="1"
              max="20"
              value={maxRank}
              onChange={e => setMaxRank(parseInt(e.target.value))}
              disabled={isRunning}
              className="w-24 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
          </div>
          <button
            onClick={startScan}
            disabled={isRunning || loading}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isRunning ? "Scanning…" : "Start Scan"}
          </button>
        </div>
        {error && (
          <p className="mt-3 text-sm text-red-600">{error}</p>
        )}
      </div>

      {/* Progress */}
      {scan && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">
              Scan {scan.status === "running" ? "in progress…" : scan.status === "complete" ? "complete" : "failed"}
            </h3>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              scan.status === "complete" ? "bg-green-100 text-green-700" :
              scan.status === "error"    ? "bg-red-100 text-red-700" :
              "bg-blue-100 text-blue-700"
            }`}>
              {scan.status}
            </span>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-gray-100 rounded-full h-2 mb-4">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${scan.progress_pct}%` }}
            />
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-lg font-bold text-gray-800">{scan.total_archer.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-0.5">Total in Archer</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-lg font-bold text-gray-800">{scan.total_filtered.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-0.5">Passed filters</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="text-lg font-bold text-gray-800">{scan.total_ranked.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-0.5">Rank checked</div>
            </div>
            <div className="bg-green-50 rounded-lg p-3">
              <div className="text-lg font-bold text-green-700">{scan.total_found.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-0.5">Top {scan.max_rank} qualified</div>
            </div>
          </div>

          {scan.error && (
            <p className="mt-3 text-sm text-red-600">Error: {scan.error}</p>
          )}
        </div>
      )}

      {/* Results table */}
      {results && results.products.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          {/* Table toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-gray-100">
            <div className="flex items-center gap-4">
              <span className="text-sm font-semibold text-gray-700">
                {results.total} qualified products
                {results.new_only < results.total && (
                  <span className="ml-2 text-gray-400 font-normal">
                    ({results.new_only} new, {results.total - results.new_only} already have campaigns)
                  </span>
                )}
              </span>
              <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={hideExisting}
                  onChange={e => setHideExisting(e.target.checked)}
                  className="rounded"
                />
                Hide existing campaigns
              </label>
            </div>
            <div className="flex gap-2">
              {selected.size > 0 && (
                <>
                  <span className="text-sm text-blue-600 font-medium self-center">
                    {selected.size} selected
                  </span>
                  <button
                    onClick={copySelected}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Copy ASINs
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <tr>
                  <th className="px-3 py-2 text-center">
                    <input
                      type="checkbox"
                      checked={selected.size === displayProducts.length && displayProducts.length > 0}
                      onChange={toggleAll}
                      className="rounded"
                    />
                  </th>
                  <th className="px-3 py-2 text-left">Product</th>
                  <th className="px-3 py-2 text-left">ASIN</th>
                  <th className="px-3 py-2 text-right">Rating</th>
                  <th className="px-3 py-2 text-right">Reviews</th>
                  <th className="px-3 py-2 text-right">Price</th>
                  <th className="px-3 py-2 text-left">Subcategory</th>
                  <th className="px-3 py-2 text-center">Rank</th>
                  <th className="px-3 py-2 text-center">Campaign</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {displayProducts.map(p => (
                  <tr
                    key={p.asin}
                    className={`hover:bg-gray-50 transition-colors ${selected.has(p.asin) ? "bg-blue-50/60" : ""}`}
                  >
                    <td className="px-3 py-2 text-center">
                      <input
                        type="checkbox"
                        checked={selected.has(p.asin)}
                        onChange={() => toggleSelect(p.asin)}
                        className="rounded"
                      />
                    </td>
                    <td className="px-3 py-2 max-w-xs">
                      <div className="flex items-center gap-2">
                        {p.image_url && (
                          <img
                            src={p.image_url}
                            alt=""
                            className="w-8 h-8 object-contain rounded flex-shrink-0"
                            onError={e => (e.currentTarget.style.display = "none")}
                          />
                        )}
                        <span className="truncate text-gray-800">{p.product_name ?? "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <a
                        href={`https://www.amazon.com/dp/${p.asin}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-blue-600 hover:underline text-xs"
                      >
                        {p.asin}
                      </a>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <StarRating rating={p.rating} />
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600">
                      {p.review_count != null ? p.review_count.toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600">
                      {p.price != null ? `$${p.price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-600 max-w-[200px]">
                      <span className="truncate block" title={p.subcategory ?? ""}>
                        {p.subcategory ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-green-100 text-green-700 font-bold text-xs">
                        #{p.rank ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      {p.has_campaign ? (
                        <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Running</span>
                      ) : (
                        <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">New</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {results && results.products.length === 0 && scan?.status === "complete" && (
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-500">
          No products found matching your criteria. Try relaxing the filters.
        </div>
      )}
    </div>
  );
}

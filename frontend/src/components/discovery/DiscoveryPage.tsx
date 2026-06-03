import { useState, useEffect, useRef } from "react";

const API = "";

interface ScanStatus {
  id: number;
  archer_status: "idle" | "running" | "complete" | "error";
  min_rating: number;
  min_reviews: number;
  result_limit: number;
  total_archer: number;
  total_filtered: number;
  archer_started_at: string | null;
  archer_finished_at: string | null;
  archer_error: string | null;
  rank_status: "idle" | "running" | "complete" | "error";
  max_rank: number;
  total_ranked: number;
  total_found: number;
  rank_started_at: string | null;
  rank_finished_at: string | null;
  rank_error: string | null;
  rank_progress_pct: number;
}

interface ProductRow {
  id: number;
  asin: string;
  product_name: string | null;
  rating: number | null;
  review_count: number | null;
  price: number | null;
  image_url: string | null;
  has_campaign: boolean;
}

interface RankedProductRow extends ProductRow {
  subcategory: string | null;
  rank: number | null;
}

interface CandidatesResponse {
  scan_id: number;
  total: number;
  new_only: number;
  products: ProductRow[];
}

interface ResultsResponse {
  scan_id: number;
  total: number;
  new_only: number;
  products: RankedProductRow[];
}

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle:     "bg-gray-100 text-gray-500",
    running:  "bg-blue-100 text-blue-700",
    complete: "bg-green-100 text-green-700",
    error:    "bg-red-100 text-red-700",
  };
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${colors[status] ?? colors.idle}`}>
      {status}
    </span>
  );
}

function Stars({ rating }: { rating: number | null }) {
  if (rating == null) return <span className="text-gray-400">—</span>;
  return <span className="text-yellow-500 font-medium">{"★".repeat(Math.floor(rating))}{"☆".repeat(5 - Math.floor(rating))} {rating.toFixed(1)}</span>;
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-full bg-gray-100 rounded-full h-2">
      <div className="bg-blue-500 h-2 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function DiscoveryPage() {
  // Settings
  const [minRating, setMinRating] = useState(4.2);
  const [minReviews, setMinReviews] = useState(100);
  const [resultLimit, setResultLimit] = useState(1000);
  const [maxRank, setMaxRank] = useState(5);

  // State
  const [scan, setScan] = useState<ScanStatus | null>(null);
  const [candidates, setCandidates] = useState<CandidatesResponse | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [hideExisting, setHideExisting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // On mount, load latest scan state
  useEffect(() => {
    loadLatest();
    return () => stopPolling();
  }, []);

  useEffect(() => {
    if (!scan) return;
    const anyRunning = scan.archer_status === "running" || scan.rank_status === "running";

    if (anyRunning) {
      startPolling();
    } else {
      stopPolling();
    }

    if (scan.archer_status === "complete" && !candidates) fetchCandidates();
    if (scan.rank_status === "complete" && !results) fetchResults();
  }, [scan?.archer_status, scan?.rank_status, scan?.id]);

  useEffect(() => {
    if (candidates) fetchCandidates();
  }, [hideExisting]);

  useEffect(() => {
    if (results) fetchResults();
  }, [hideExisting]);

  async function loadLatest() {
    try {
      const r = await fetch(`${API}/api/discovery/scan/latest`);
      if (r.ok) {
        const data = await r.json();
        setScan(data);
      }
    } catch { /* no scan yet */ }
  }

  async function fetchCandidates() {
    try {
      const r = await fetch(`${API}/api/discovery/candidates?hide_existing=${hideExisting}`);
      if (r.ok) setCandidates(await r.json());
    } catch (e) { console.error(e); }
  }

  async function fetchResults() {
    try {
      const r = await fetch(`${API}/api/discovery/results?hide_existing=${hideExisting}`);
      if (r.ok) setResults(await r.json());
    } catch (e) { console.error(e); }
  }

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const r = await fetch(`${API}/api/discovery/scan/latest`);
      if (r.ok) {
        const data: ScanStatus = await r.json();
        setScan(data);
        if (data.archer_status === "complete") fetchCandidates();
        if (data.rank_status === "complete") fetchResults();
      }
    }, 2000);
  }

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  async function startArcherScan() {
    setCandidates(null);
    setResults(null);
    setSelected(new Set());
    const r = await fetch(`${API}/api/discovery/scan/archer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ min_rating: minRating, min_reviews: minReviews, result_limit: resultLimit }),
    });
    if (!r.ok) {
      const d = await r.json();
      alert(d.detail || "Failed to start Archer scan");
      return;
    }
    setScan(await r.json());
    startPolling();
  }

  async function startRankScan() {
    setResults(null);
    setSelected(new Set());
    const r = await fetch(`${API}/api/discovery/scan/rank`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_rank: maxRank }),
    });
    if (!r.ok) {
      const d = await r.json();
      alert(d.detail || "Failed to start ranking scan");
      return;
    }
    setScan(await r.json());
    startPolling();
  }

  function toggleSelect(asin: string) {
    setSelected(prev => { const n = new Set(prev); n.has(asin) ? n.delete(asin) : n.add(asin); return n; });
  }
  function toggleAll(items: { asin: string }[]) {
    setSelected(prev => prev.size === items.length ? new Set() : new Set(items.map(p => p.asin)));
  }
  function copySelected() {
    navigator.clipboard.writeText(Array.from(selected).join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const archerRunning = scan?.archer_status === "running";
  const rankRunning   = scan?.rank_status === "running";
  const archerDone    = scan?.archer_status === "complete";
  const rankDone      = scan?.rank_status === "complete";

  return (
    <div className="space-y-6 p-4">
      <div>
        <h2 className="text-xl font-semibold text-gray-800">Product Discovery</h2>
        <p className="text-sm text-gray-500 mt-1">
          Two-step scan: filter the Archer catalog, then check Amazon subcategory rankings.
        </p>
      </div>

      {/* ── Phase 1: Archer Scan ─────────────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <span className="flex items-center justify-center w-7 h-7 rounded-full bg-blue-600 text-white text-xs font-bold">1</span>
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Archer Catalog Scan</h3>
              <p className="text-xs text-gray-500">Fetch all products · filter by rating &amp; reviews · fast</p>
            </div>
          </div>
          <Badge status={scan?.archer_status ?? "idle"} />
        </div>

        <div className="px-5 py-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Min. Rating</label>
              <input type="number" step="0.1" min="1" max="5" value={minRating}
                onChange={e => setMinRating(parseFloat(e.target.value))}
                disabled={archerRunning}
                className="w-24 border border-gray-300 rounded-lg px-3 py-1.5 text-sm disabled:opacity-50" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Min. Reviews</label>
              <input type="number" step="10" min="0" value={minReviews}
                onChange={e => setMinReviews(parseInt(e.target.value))}
                disabled={archerRunning}
                className="w-28 border border-gray-300 rounded-lg px-3 py-1.5 text-sm disabled:opacity-50" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Stop after N results</label>
              <input type="number" step="100" min="10" value={resultLimit}
                onChange={e => setResultLimit(parseInt(e.target.value))}
                disabled={archerRunning}
                className="w-28 border border-gray-300 rounded-lg px-3 py-1.5 text-sm disabled:opacity-50" />
            </div>
            <button onClick={startArcherScan} disabled={archerRunning}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {archerRunning ? "Scanning…" : archerDone ? "Re-scan Archer" : "Scan Archer Catalog"}
            </button>
          </div>

          {scan && scan.archer_status !== "idle" && (
            <div className="mt-4 space-y-3">
              {archerRunning && <ProgressBar pct={50} />}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="text-lg font-bold text-gray-800">{scan.total_archer.toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Scanned from Archer</div>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="text-lg font-bold text-gray-800">{scan.total_filtered.toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Passed filter</div>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="text-lg font-bold text-gray-800">{scan.result_limit.toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Limit</div>
                </div>
                {archerDone && (
                  <div className={`rounded-lg p-3 ${scan.total_filtered >= scan.result_limit ? "bg-amber-50" : "bg-green-50"}`}>
                    <div className={`text-lg font-bold ${scan.total_filtered >= scan.result_limit ? "text-amber-700" : "text-green-700"}`}>
                      {scan.total_filtered >= scan.result_limit ? "Stopped early" : "Full scan"}
                    </div>
                    <div className="text-xs text-gray-500">
                      {scan.total_filtered >= scan.result_limit
                        ? `${scan.total_archer.toLocaleString()} scanned`
                        : `${Math.round(scan.total_filtered / Math.max(scan.total_archer,1) * 100)}% pass rate`}
                    </div>
                  </div>
                )}
              </div>
              {scan.archer_error && <p className="text-sm text-red-600">Error: {scan.archer_error}</p>}
            </div>
          )}
        </div>
      </div>

      {/* ── Phase 1 Results: Candidate Table ─────────────────────────────── */}
      {candidates && candidates.products.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-gray-100">
            <span className="text-sm font-semibold text-gray-700">
              {candidates.total.toLocaleString()} products passed filter
              {candidates.new_only < candidates.total && (
                <span className="ml-2 text-gray-400 font-normal text-xs">
                  ({candidates.new_only} new · {candidates.total - candidates.new_only} already have campaigns)
                </span>
              )}
            </span>
            <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" checked={hideExisting} onChange={e => setHideExisting(e.target.checked)} className="rounded" />
              Hide existing campaigns
            </label>
          </div>
          <div className="overflow-x-auto max-h-72">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left">Product</th>
                  <th className="px-3 py-2 text-left">ASIN</th>
                  <th className="px-3 py-2 text-right">Rating</th>
                  <th className="px-3 py-2 text-right">Reviews</th>
                  <th className="px-3 py-2 text-right">Price</th>
                  <th className="px-3 py-2 text-center">Campaign</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {candidates.products.map(p => (
                  <tr key={p.asin} className="hover:bg-gray-50">
                    <td className="px-3 py-2 max-w-xs">
                      <div className="flex items-center gap-2">
                        {p.image_url && <img src={p.image_url} alt="" className="w-7 h-7 object-contain rounded flex-shrink-0" onError={e => (e.currentTarget.style.display = "none")} />}
                        <span className="truncate text-gray-800 text-xs">{p.product_name ?? "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <a href={`https://www.amazon.com/dp/${p.asin}`} target="_blank" rel="noopener noreferrer"
                        className="font-mono text-blue-600 hover:underline text-xs">{p.asin}</a>
                    </td>
                    <td className="px-3 py-2 text-right"><Stars rating={p.rating} /></td>
                    <td className="px-3 py-2 text-right text-gray-600 text-xs">{p.review_count?.toLocaleString() ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-gray-600 text-xs">{p.price != null ? `$${p.price.toFixed(2)}` : "—"}</td>
                    <td className="px-3 py-2 text-center">
                      {p.has_campaign
                        ? <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Running</span>
                        : <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">New</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Phase 2: Ranking Scan ─────────────────────────────────────────── */}
      <div className={`bg-white border rounded-xl shadow-sm overflow-hidden transition-opacity ${archerDone ? "border-gray-200 opacity-100" : "border-gray-100 opacity-40 pointer-events-none"}`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <span className="flex items-center justify-center w-7 h-7 rounded-full bg-purple-600 text-white text-xs font-bold">2</span>
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Amazon Ranking Check</h3>
              <p className="text-xs text-gray-500">Check BSR via Rainforest API · ~0.5s per product · costs API credits</p>
            </div>
          </div>
          <Badge status={scan?.rank_status ?? "idle"} />
        </div>

        <div className="px-5 py-4">
          <div className="flex flex-wrap gap-4 items-end">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Top N in Subcategory</label>
              <input type="number" step="1" min="1" max="20" value={maxRank}
                onChange={e => setMaxRank(parseInt(e.target.value))}
                disabled={rankRunning}
                className="w-24 border border-gray-300 rounded-lg px-3 py-1.5 text-sm disabled:opacity-50" />
            </div>
            <button onClick={startRankScan} disabled={rankRunning || !archerDone}
              className="px-5 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors">
              {rankRunning ? `Checking… ${scan?.total_ranked ?? 0} / ${scan?.total_filtered ?? "?"}` :
               rankDone ? "Re-check Rankings" : "Check Amazon Rankings"}
            </button>
            {scan?.total_filtered && !rankRunning && (
              <span className="text-xs text-gray-400 self-center">
                ~{Math.round((scan.total_filtered * 0.5) / 60)} min estimated
              </span>
            )}
          </div>

          {scan && scan.rank_status !== "idle" && (
            <div className="mt-4 space-y-3">
              <ProgressBar pct={scan.rank_progress_pct} />
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-center">
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="text-lg font-bold text-gray-800">{scan.total_ranked.toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Checked</div>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <div className="text-lg font-bold text-gray-800">{scan.total_filtered.toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Total to check</div>
                </div>
                <div className="bg-purple-50 rounded-lg p-3">
                  <div className="text-lg font-bold text-purple-700">{scan.total_found.toLocaleString()}</div>
                  <div className="text-xs text-gray-500">Top {scan.max_rank} qualified</div>
                </div>
              </div>
              {scan.rank_error && <p className="text-sm text-red-600">Error: {scan.rank_error}</p>}
            </div>
          )}
        </div>
      </div>

      {/* ── Phase 2 Results: Qualified Products ──────────────────────────── */}
      {results && results.products.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-gray-100">
            <div className="flex items-center gap-4">
              <span className="text-sm font-semibold text-gray-700">
                {results.total} qualified products
                {results.new_only < results.total && (
                  <span className="ml-2 text-gray-400 font-normal text-xs">
                    ({results.new_only} new · {results.total - results.new_only} already have campaigns)
                  </span>
                )}
              </span>
              <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
                <input type="checkbox" checked={hideExisting} onChange={e => setHideExisting(e.target.checked)} className="rounded" />
                Hide existing
              </label>
            </div>
            <div className="flex items-center gap-2">
              {selected.size > 0 && (
                <>
                  <span className="text-sm text-purple-600 font-medium">{selected.size} selected</span>
                  <button onClick={copySelected}
                    className={`px-3 py-1.5 text-sm border rounded-lg transition-colors ${copied ? "bg-green-50 border-green-300 text-green-700" : "border-gray-300 hover:bg-gray-50"}`}>
                    {copied ? "Copied!" : "Copy ASINs"}
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
                    <input type="checkbox"
                      checked={selected.size === results.products.length && results.products.length > 0}
                      onChange={() => toggleAll(results.products)} className="rounded" />
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
                {results.products.map(p => (
                  <tr key={p.asin} className={`hover:bg-gray-50 transition-colors ${selected.has(p.asin) ? "bg-purple-50/50" : ""}`}>
                    <td className="px-3 py-2 text-center">
                      <input type="checkbox" checked={selected.has(p.asin)} onChange={() => toggleSelect(p.asin)} className="rounded" />
                    </td>
                    <td className="px-3 py-2 max-w-xs">
                      <div className="flex items-center gap-2">
                        {p.image_url && <img src={p.image_url} alt="" className="w-8 h-8 object-contain rounded flex-shrink-0" onError={e => (e.currentTarget.style.display = "none")} />}
                        <span className="truncate text-gray-800">{p.product_name ?? "—"}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <a href={`https://www.amazon.com/dp/${p.asin}`} target="_blank" rel="noopener noreferrer"
                        className="font-mono text-blue-600 hover:underline text-xs">{p.asin}</a>
                    </td>
                    <td className="px-3 py-2 text-right"><Stars rating={p.rating} /></td>
                    <td className="px-3 py-2 text-right text-gray-600 text-xs">{p.review_count?.toLocaleString() ?? "—"}</td>
                    <td className="px-3 py-2 text-right text-gray-600 text-xs">{p.price != null ? `$${p.price.toFixed(2)}` : "—"}</td>
                    <td className="px-3 py-2 text-gray-600 max-w-[200px]">
                      <span className="truncate block text-xs" title={p.subcategory ?? ""}>{p.subcategory ?? "—"}</span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-green-100 text-green-700 font-bold text-xs">
                        #{p.rank ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      {p.has_campaign
                        ? <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Running</span>
                        : <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">New</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {results && results.products.length === 0 && rankDone && (
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center text-gray-500 text-sm">
          No products ranked in the top {scan?.max_rank} of their subcategory. Try increasing the rank limit.
        </div>
      )}
    </div>
  );
}

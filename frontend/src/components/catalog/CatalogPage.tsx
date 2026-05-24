import { useState, useEffect, useCallback } from "react";
import {
  fetchCatalogProducts,
  fetchCatalogSyncStatus,
  triggerCatalogSync,
  generateCampaignDrafts,
} from "../../api/client";
import type { ProductCatalogItem, CatalogSyncStatus } from "../../types";

const MARKETS = ["All", "UK", "DE", "JP", "CA"] as const;
type Market = (typeof MARKETS)[number];

export function CatalogPage() {
  const [market, setMarket] = useState<Market>("All");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<ProductCatalogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [syncStatus, setSyncStatus] = useState<CatalogSyncStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set()); // "ASIN|COUNTRY"
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const cc = market === "All" ? "" : market;
      const result = await fetchCatalogProducts(cc, search);
      setItems(result.items);
      setTotal(result.total);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [market, search]);

  const loadSyncStatus = useCallback(async () => {
    try {
      const s = await fetchCatalogSyncStatus();
      setSyncStatus(s);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadSyncStatus();
  }, [loadSyncStatus]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await triggerCatalogSync();
      setTimeout(() => { loadSyncStatus(); setSyncing(false); }, 3000);
    } catch {
      setSyncing(false);
    }
  };

  const toggleSelect = (asin: string, cc: string) => {
    const key = `${asin}|${cc}`;
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const handleCreateCampaigns = async () => {
    if (selected.size === 0) return;
    setCreating(true);
    setCreateMsg("");
    try {
      const items = Array.from(selected).map((key) => {
        const [asin, country_code] = key.split("|");
        return { asin, country_code };
      });
      const drafts = await generateCampaignDrafts(items);
      setCreateMsg(`${drafts.length} campaign draft(s) created. Go to the Campaigns tab to export.`);
      setSelected(new Set());
    } catch {
      setCreateMsg("Failed to create campaigns. Please try again.");
    } finally {
      setCreating(false);
    }
  };

  const thBase = "px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap";
  const tdBase = "px-3 py-2 text-xs text-gray-800 whitespace-nowrap";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Non-US Product Catalog</h2>
          <p className="text-xs text-gray-500 mt-0.5">{total} products available</p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <button
              onClick={handleCreateCampaigns}
              disabled={creating}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {creating ? "Creating..." : `Create ${selected.size} Campaign(s)`}
            </button>
          )}
          <button
            onClick={handleSync}
            disabled={syncing}
            className="px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {syncing ? "Syncing..." : "↻ Sync Catalog"}
          </button>
        </div>
      </div>

      {createMsg && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-2 text-sm text-blue-700">
          {createMsg}
        </div>
      )}

      {/* Sync status chips */}
      {syncStatus.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {syncStatus.map((s) => (
            <span key={s.country_code} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600">
              {s.country_code}: {s.records} products
              {s.last_synced_at && (
                <span className="text-gray-400">· {new Date(s.last_synced_at).toLocaleDateString()}</span>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Controls */}
      <div className="flex flex-wrap gap-3 items-center">
        {/* Market filter */}
        <div className="flex rounded-md border border-gray-300 overflow-hidden text-xs font-medium">
          {MARKETS.map((m) => (
            <button
              key={m}
              onClick={() => setMarket(m)}
              className={`px-3 py-1.5 transition-colors ${
                market === m ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
              } ${m !== "All" ? "border-l border-gray-300" : ""}`}
            >
              {m}
            </button>
          ))}
        </div>
        {/* Search */}
        <input
          type="text"
          placeholder="Search product or ASIN..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {selected.size > 0 && (
          <button onClick={() => setSelected(new Set())} className="text-xs text-gray-400 hover:text-gray-600">
            Clear selection ({selected.size})
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-x-auto">
        {loading ? (
          <div className="h-48 animate-pulse bg-gray-50" />
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className={thBase} style={{ width: 32 }} />
                <th className={thBase}>Market</th>
                <th className={thBase}>ASIN</th>
                <th className={thBase}>Product</th>
                <th className={`${thBase} text-right`}>Price</th>
                <th className={`${thBase} text-right`}>Rating</th>
                <th className={`${thBase} text-right`}>Reviews</th>
                <th className={thBase}>Availability</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-400 text-sm">
                    {total === 0 ? "No products found. Click \"Sync Catalog\" to import products." : "No products match your filters."}
                  </td>
                </tr>
              )}
              {items.map((item) => {
                const key = `${item.asin}|${item.country_code}`;
                const isSelected = selected.has(key);
                return (
                  <tr key={key} className={`hover:bg-gray-50 transition-colors ${isSelected ? "bg-blue-50" : ""}`}>
                    <td className={tdBase}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(item.asin, item.country_code)}
                        className="rounded border-gray-300 text-blue-600"
                      />
                    </td>
                    <td className={tdBase}>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-600">
                        {item.country_code}
                      </span>
                    </td>
                    <td className={`${tdBase} font-mono text-gray-500`}>{item.asin}</td>
                    <td className={tdBase} style={{ maxWidth: 260 }}>
                      <div className="flex items-center gap-2">
                        {item.image_url && (
                          <img src={item.image_url} alt="" className="w-8 h-8 object-contain rounded" />
                        )}
                        <span className="truncate" title={item.product_name ?? ""}>{item.product_name ?? "—"}</span>
                      </div>
                    </td>
                    <td className={`${tdBase} text-right`}>{item.price != null ? `$${item.price.toFixed(2)}` : "—"}</td>
                    <td className={`${tdBase} text-right`}>{item.rating != null ? item.rating.toFixed(1) : "—"}</td>
                    <td className={`${tdBase} text-right`}>{item.review_count != null ? item.review_count.toLocaleString() : "—"}</td>
                    <td className={tdBase}>
                      {item.availability ? (
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          item.availability.toLowerCase().includes("in stock")
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}>
                          {item.availability}
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="text-xs text-gray-400">{items.length} of {total} products shown</div>
    </div>
  );
}

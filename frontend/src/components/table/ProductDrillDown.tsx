import { useEffect, useState } from "react";
import { fetchCampaignProducts } from "../../api/client";
import { fmtUSD, fmtNumber, fmtPct } from "../../utils/formatters";
import type { CampaignProduct } from "../../types";

interface Props {
  campaignId: string;
  dateFrom: string;
  dateTo: string;
  colSpan: number;
  /** Spin up a campaign for a halo ASIN (pre-fills the Create Campaigns tab). */
  onCreateForAsin: (asin: string, productName: string | null) => void;
}

export function ProductDrillDown({ campaignId, dateFrom, dateTo, colSpan, onCreateForAsin }: Props) {
  const [products, setProducts] = useState<CampaignProduct[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchCampaignProducts(campaignId, dateFrom, dateTo)
      .then((r) => { if (!cancelled) setProducts(r.products); })
      .catch(() => { if (!cancelled) setProducts([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [campaignId, dateFrom, dateTo]);

  const cell = "px-8 py-2 bg-blue-50/30";

  if (loading) {
    return <tr><td colSpan={colSpan} className={`${cell} text-xs text-gray-400`}>Loading products…</td></tr>;
  }
  if (!products || !products.length) {
    return <tr><td colSpan={colSpan} className={`${cell} text-xs text-gray-400 italic`}>
      No product-level data (new-API only, from Jun 7).
    </td></tr>;
  }

  return (
    <tr>
      <td colSpan={colSpan} className="px-8 py-3 bg-blue-50/30">
        <div className="text-[11px] text-gray-500 mb-1.5 font-medium">Products actually sold under this campaign's link</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 text-[10px] uppercase tracking-wider">
              <th className="text-left font-semibold py-1">Sold ASIN</th>
              <th className="text-left font-semibold py-1">Product</th>
              <th className="text-right font-semibold py-1">Units</th>
              <th className="text-right font-semibold py-1">Sales</th>
              <th className="text-right font-semibold py-1">Commission</th>
              <th className="text-right font-semibold py-1">% of camp</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.sold_asin} className="border-t border-blue-100/50">
                <td className="py-1.5 font-mono text-gray-700">
                  {p.sold_asin}
                  {p.is_own && (
                    <span className="ml-1.5 inline-block px-1 py-0.5 rounded text-[9px] bg-gray-200 text-gray-600">own</span>
                  )}
                </td>
                <td className="py-1.5 text-gray-600 max-w-md truncate" title={p.product_name ?? ""}>
                  {p.product_name ?? "—"}
                </td>
                <td className="py-1.5 text-right text-gray-700">{fmtNumber(p.units)}</td>
                <td className="py-1.5 text-right text-gray-700">{fmtUSD(p.sales)}</td>
                <td className="py-1.5 text-right font-medium text-gray-800">{fmtUSD(p.commission)}</td>
                <td className="py-1.5 text-right text-gray-500">{fmtPct(p.pct_of_commission)}</td>
                <td className="py-1.5 text-right">
                  {!p.is_own && p.commission > 0 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onCreateForAsin(p.sold_asin, p.product_name); }}
                      className="px-2 py-0.5 text-[10px] font-medium rounded border border-blue-300 text-blue-600 hover:bg-blue-100"
                      title={`Create a campaign targeting ${p.sold_asin}`}
                    >
                      🚀 Create campaign
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </td>
    </tr>
  );
}

import { markActionApplied, resetAppliedAction } from "../../api/client";
import type { TestCampaignStatus, TestAction } from "../../types";

interface Props {
  campaigns: TestCampaignStatus[];
  loading: boolean;
  onChange: () => void;
}

const ACTION_STYLES: Record<TestAction, string> = {
  cut:        "bg-red-100 text-red-700",
  scale_bid:  "bg-blue-100 text-blue-700",
  mature_bid: "bg-purple-100 text-purple-700",
  testing:    "bg-yellow-50 text-yellow-700",
  no_data:    "bg-gray-100 text-gray-500",
  completed:  "bg-green-100 text-green-700",
};

const ACTION_LABELS: Record<TestAction, string> = {
  cut:        "Cut",
  scale_bid:  "Scale bid",
  mature_bid: "Mature bid",
  testing:    "Testing",
  no_data:    "No data",
  completed:  "Completed",
};

const ACTIONABLE = new Set<TestAction>(["cut", "scale_bid", "mature_bid"]);

function fmt(n: number | null, prefix = "", decimals = 2): string {
  if (n === null || n === undefined) return "—";
  return `${prefix}${n.toFixed(decimals)}`;
}

export function TestingTable({ campaigns, loading, onChange }: Props) {
  async function handleMarkApplied(c: TestCampaignStatus) {
    if (!ACTIONABLE.has(c.action)) return;
    await markActionApplied(c.id, c.action as "cut" | "scale_bid" | "mature_bid");
    onChange();
  }
  async function handleReset(id: number) {
    await resetAppliedAction(id);
    onChange();
  }
  if (loading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">
        Loading...
      </div>
    );
  }

  if (campaigns.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">
        No test campaigns yet. Upload a batch CSV above to start.
      </div>
    );
  }

  // Sort: action items first, then testing, no_data, completed last
  const order: TestAction[] = ["cut", "scale_bid", "mature_bid", "testing", "no_data", "completed"];
  const sorted = [...campaigns].sort(
    (a, b) => order.indexOf(a.action) - order.indexOf(b.action)
  );

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Campaign</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">ASIN</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">AOV</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Threshold</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Clicks</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Orders</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Spend</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">CPC</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">RPC</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600">Action</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">New Bid</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Reason</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((c) => (
              <tr key={c.id} className="hover:bg-gray-50">
                <td className="px-4 py-2.5 font-medium text-gray-900 max-w-xs truncate">
                  {c.campaign_name}
                </td>
                <td className="px-4 py-2.5 text-gray-500 font-mono text-xs">
                  {c.asin ?? "—"}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-700">
                  ${c.expected_aov.toFixed(2)}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-500">
                  {c.cut_threshold}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-700">{c.clicks}</td>
                <td className="px-4 py-2.5 text-right text-gray-700">{c.orders}</td>
                <td className="px-4 py-2.5 text-right text-gray-700">
                  ${c.spend_usd.toFixed(2)}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-700">
                  {fmt(c.cpc, "$")}
                </td>
                <td className="px-4 py-2.5 text-right text-gray-700">
                  {fmt(c.rpc, "$")}
                </td>
                <td className="px-4 py-2.5 text-center">
                  <span
                    className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                      ACTION_STYLES[c.action]
                    }`}
                  >
                    {ACTION_LABELS[c.action]}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-medium text-blue-700">
                  {c.new_bid !== null ? `$${c.new_bid.toFixed(2)}` : "—"}
                </td>
                <td className="px-4 py-2.5 text-gray-500 text-xs max-w-xs">
                  {c.action_reason}
                </td>
                <td className="px-4 py-2.5 text-center">
                  {ACTIONABLE.has(c.action) ? (
                    <button
                      onClick={() => handleMarkApplied(c)}
                      className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-700 whitespace-nowrap"
                    >
                      Mark applied
                    </button>
                  ) : c.action === "completed" && c.action_reason.includes("applied") ? (
                    <button
                      onClick={() => handleReset(c.id)}
                      className="text-xs px-2 py-1 rounded text-gray-400 hover:text-gray-600 whitespace-nowrap"
                    >
                      Undo
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

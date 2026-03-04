const STATUS_OPTIONS = ["All", "Enabled", "Paused", "Removed"] as const;
type StatusOption = (typeof STATUS_OPTIONS)[number];

interface Props {
  campaignFilter: string;
  asinFilter: string;
  statusFilter: StatusOption;
  onCampaignChange: (v: string) => void;
  onAsinChange: (v: string) => void;
  onStatusChange: (v: StatusOption) => void;
}

export type { StatusOption };

export function TableFilters({
  campaignFilter,
  asinFilter,
  statusFilter,
  onCampaignChange,
  onAsinChange,
  onStatusChange,
}: Props) {
  return (
    <div className="flex gap-3 flex-wrap items-center">
      <input
        type="text"
        placeholder="Filter campaign..."
        value={campaignFilter}
        onChange={(e) => onCampaignChange(e.target.value)}
        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <input
        type="text"
        placeholder="Filter ASIN..."
        value={asinFilter}
        onChange={(e) => onAsinChange(e.target.value)}
        className="border border-gray-300 rounded-md px-3 py-1.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      <div className="flex rounded-md border border-gray-300 overflow-hidden text-xs font-medium">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt}
            onClick={() => onStatusChange(opt)}
            className={`px-3 py-1.5 transition-colors ${
              statusFilter === opt
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-600 hover:bg-gray-50"
            } ${opt !== "All" ? "border-l border-gray-300" : ""}`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}

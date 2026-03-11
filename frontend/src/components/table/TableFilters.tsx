const STATUS_OPTIONS = ["All", "Enabled", "Paused", "Removed"] as const;
type StatusOption = (typeof STATUS_OPTIONS)[number];

interface Props {
  campaignFilter: string;
  asinFilter: string;
  statusFilter: StatusOption;
  ageMin: number | "";
  ageMax: number | "";
  onCampaignChange: (v: string) => void;
  onAsinChange: (v: string) => void;
  onStatusChange: (v: StatusOption) => void;
  onAgeMinChange: (v: number | "") => void;
  onAgeMaxChange: (v: number | "") => void;
}

export type { StatusOption };

function parseDay(val: string): number | "" {
  return val === "" ? "" : Math.max(0, parseInt(val, 10) || 0);
}

export function TableFilters({
  campaignFilter,
  asinFilter,
  statusFilter,
  ageMin,
  ageMax,
  onCampaignChange,
  onAsinChange,
  onStatusChange,
  onAgeMinChange,
  onAgeMaxChange,
}: Props) {
  const hasAgeFilter = ageMin !== "" || ageMax !== "";

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
      {/* Status filter */}
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
      {/* Age range filter */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-gray-500 whitespace-nowrap">Age</span>
        <input
          type="number"
          min={0}
          placeholder="min"
          value={ageMin}
          onChange={(e) => onAgeMinChange(parseDay(e.target.value))}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-xs w-16 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <span className="text-xs text-gray-400">–</span>
        <input
          type="number"
          min={0}
          placeholder="max"
          value={ageMax}
          onChange={(e) => onAgeMaxChange(parseDay(e.target.value))}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-xs w-16 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <span className="text-xs text-gray-500">d</span>
        {hasAgeFilter && (
          <button
            onClick={() => { onAgeMinChange(""); onAgeMaxChange(""); }}
            className="text-xs text-gray-400 hover:text-gray-600"
            title="Clear age filter"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}

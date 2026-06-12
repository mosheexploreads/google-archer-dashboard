import type { RevenueSource } from "../../types";

interface Props {
  value: RevenueSource;
  onChange: (s: RevenueSource) => void;
}

const OPTIONS: { value: RevenueSource; label: string; title: string }[] = [
  {
    value: "auto",
    label: "Auto",
    title: "Old API before Jun 7, 2026 (Archer's commission change), new API from then on",
  },
  { value: "legacy", label: "Old API",  title: "Deprecated /product_reports_all — pre-change commission model" },
  { value: "new",    label: "New API",  title: "/reports v2 — link-attributed (direct + halo), current commission model" },
];

export function SourceToggle({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 whitespace-nowrap">Revenue</span>
      <div className="flex rounded-md border border-gray-300 overflow-hidden">
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            title={opt.title}
            className={`px-3 py-1.5 text-sm font-medium transition-colors ${
              value === opt.value
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-700 hover:bg-gray-50"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

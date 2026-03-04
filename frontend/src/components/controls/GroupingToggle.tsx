import type { GroupBy } from "../../types";

interface Props {
  value: GroupBy;
  onChange: (g: GroupBy) => void;
}

const OPTIONS: { value: GroupBy; label: string }[] = [
  { value: "day",   label: "Day" },
  { value: "week",  label: "Week" },
  { value: "month", label: "Month" },
];

export function GroupingToggle({ value, onChange }: Props) {
  return (
    <div className="flex rounded-md border border-gray-300 overflow-hidden">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
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
  );
}

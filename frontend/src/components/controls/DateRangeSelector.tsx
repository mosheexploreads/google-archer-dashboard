import type { DateRange } from "../../types";

interface Preset {
  label: string;
  from: () => string;
  to: () => string;
}

function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toISO(d);
}

function startOfMonth(): string {
  const d = new Date();
  d.setDate(1);
  return toISO(d);
}

const PRESETS: Preset[] = [
  { label: "Yesterday", from: () => daysAgo(1), to: () => daysAgo(1) },
  { label: "L7D",       from: () => daysAgo(7), to: () => daysAgo(1) },
  { label: "L14D",      from: () => daysAgo(14), to: () => daysAgo(1) },
  { label: "L30D",      from: () => daysAgo(30), to: () => daysAgo(1) },
  { label: "MTD",       from: () => startOfMonth(), to: () => daysAgo(1) },
];

interface Props {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

export function DateRangeSelector({ value, onChange }: Props) {
  const activePreset = PRESETS.find(
    (p) => p.from() === value.from && p.to() === value.to
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      {PRESETS.map((preset) => (
        <button
          key={preset.label}
          onClick={() => onChange({ from: preset.from(), to: preset.to() })}
          className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
            activePreset?.label === preset.label
              ? "bg-blue-600 text-white"
              : "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50"
          }`}
        >
          {preset.label}
        </button>
      ))}
      <div className="flex items-center gap-1.5 ml-2">
        <input
          type="date"
          value={value.from}
          onChange={(e) => onChange({ ...value, from: e.target.value })}
          className="border border-gray-300 rounded-md px-2 py-1 text-sm"
        />
        <span className="text-gray-500 text-sm">to</span>
        <input
          type="date"
          value={value.to}
          onChange={(e) => onChange({ ...value, to: e.target.value })}
          className="border border-gray-300 rounded-md px-2 py-1 text-sm"
        />
      </div>
    </div>
  );
}

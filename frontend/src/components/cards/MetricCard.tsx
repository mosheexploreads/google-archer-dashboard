interface Props {
  label: string;
  value: string;
  subValue?: string;
}

export function MetricCard({ label, value, subValue }: Props) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
      <p className="text-sm text-gray-500 font-medium mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {subValue && (
        <p className="text-xs text-gray-400 mt-1">{subValue}</p>
      )}
    </div>
  );
}

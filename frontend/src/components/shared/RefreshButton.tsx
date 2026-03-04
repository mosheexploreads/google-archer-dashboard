interface Props {
  onClick: () => void;
  loading: boolean;
}

export function RefreshButton({ onClick, loading }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      <span
        className={`inline-block transition-transform ${loading ? "animate-spin" : ""}`}
        aria-hidden
      >
        ↻
      </span>
      {loading ? "Syncing..." : "Refresh Now"}
    </button>
  );
}

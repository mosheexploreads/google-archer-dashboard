import { fmtRelativeTime } from "../../utils/formatters";
import type { SyncStatus } from "../../types";

interface Props {
  syncStatus: SyncStatus | null;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function LastUpdated({ syncStatus }: Props) {
  const archerSync = syncStatus?.archer?.last_sync ?? null;
  const gadsThrough = syncStatus?.google_ads_data_through ?? null;

  return (
    <span className="flex items-center gap-3 text-sm text-gray-500">
      {gadsThrough ? (
        <span>
          Google Ads through:{" "}
          <span className="font-medium text-gray-700">{fmtDate(gadsThrough)}</span>
        </span>
      ) : (
        <span className="text-amber-600 font-medium">No Google Ads data uploaded</span>
      )}
      <span className="text-gray-300">|</span>
      <span>
        Archer synced:{" "}
        <span className="font-medium">{fmtRelativeTime(archerSync)}</span>
      </span>
    </span>
  );
}

import { fmtRelativeTime } from "../../utils/formatters";
import type { SyncStatus } from "../../types";

interface Props {
  syncStatus: SyncStatus | null;
}

export function LastUpdated({ syncStatus }: Props) {
  const lastSync =
    syncStatus?.google_ads?.last_sync ?? syncStatus?.archer?.last_sync ?? null;
  return (
    <span className="text-sm text-gray-500">
      Last synced: <span className="font-medium">{fmtRelativeTime(lastSync)}</span>
    </span>
  );
}

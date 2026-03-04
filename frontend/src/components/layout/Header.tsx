import { LastUpdated } from "../shared/LastUpdated";
import { RefreshButton } from "../shared/RefreshButton";
import type { SyncStatus } from "../../types";

interface Props {
  syncStatus: SyncStatus | null;
  onRefresh: () => void;
  refreshing: boolean;
}

export function Header({ syncStatus, onRefresh, refreshing }: Props) {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm">
      <h1 className="text-xl font-bold text-gray-800">Ads Dashboard</h1>
      <div className="flex items-center gap-4">
        <LastUpdated syncStatus={syncStatus} />
        <RefreshButton onClick={onRefresh} loading={refreshing} />
      </div>
    </header>
  );
}

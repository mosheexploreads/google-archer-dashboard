import { useState, useCallback } from "react";
import { fetchSyncStatus, triggerSync } from "../api/client";
import type { SyncStatus } from "../types";

export function useRefresh(onRefreshComplete?: () => void) {
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [triggering, setTriggering] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const status = await fetchSyncStatus();
      setSyncStatus(status);
    } catch {
      // non-critical
    }
  }, []);

  const handleTrigger = useCallback(async () => {
    setTriggering(true);
    try {
      await triggerSync();
      // Poll until the backend reports sync is no longer running (max 60s)
      const deadline = Date.now() + 60_000;
      while (Date.now() < deadline) {
        await new Promise((res) => setTimeout(res, 2000));
        try {
          const status = await fetchSyncStatus();
          setSyncStatus(status);
          if (!status.is_syncing) break;
        } catch {
          break;
        }
      }
      onRefreshComplete?.();
    } finally {
      setTriggering(false);
    }
  }, [onRefreshComplete, loadStatus]);

  return { syncStatus, loadStatus, handleTrigger, triggering };
}

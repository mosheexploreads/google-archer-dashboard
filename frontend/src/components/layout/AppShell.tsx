import React from "react";
import { Header } from "./Header";
import type { SyncStatus } from "../../types";

interface Props {
  syncStatus: SyncStatus | null;
  onRefresh: () => void;
  refreshing: boolean;
  children: React.ReactNode;
}

export function AppShell({ syncStatus, onRefresh, refreshing, children }: Props) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header syncStatus={syncStatus} onRefresh={onRefresh} refreshing={refreshing} />
      <main className="max-w-screen-xl mx-auto px-6 py-6 space-y-6">
        {children}
      </main>
    </div>
  );
}

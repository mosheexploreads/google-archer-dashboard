import { useState } from "react";
import type { ProductWarning } from "../../types";

interface Props {
  warnings: ProductWarning[];
}

export function WarningBanner({ warnings }: Props) {
  const [dismissed, setDismissed] = useState(false);

  if (!warnings.length || dismissed) return null;

  return (
    <div className="bg-amber-50 border border-amber-300 rounded-lg px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-amber-800">
            ⚠️ {warnings.length} enabled campaign{warnings.length > 1 ? "s" : ""}{" "}
            {warnings.length > 1 ? "have" : "has"} stopped appearing on Archer — the product may have been removed
          </p>
          <ul className="mt-2 space-y-1">
            {warnings.map((w) => (
              <li key={w.asin + w.campaign_name} className="text-sm text-amber-700">
                <span className="font-medium">{w.campaign_name}</span>
                <span className="text-amber-500"> ({w.asin})</span>
                {" — "}last seen {w.last_archer_date}{" "}
                <span className="text-amber-600">({w.days_missing} days ago)</span>
              </li>
            ))}
          </ul>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-amber-400 hover:text-amber-700 text-xl leading-none flex-shrink-0"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
    </div>
  );
}

import { useState, useEffect, useRef } from "react";
import { fetchCampaignDates } from "../api/client";
import type { DateRow, GroupBy } from "../types";

/**
 * Fetches date drill-down rows for a single campaign.
 * Results are cached by (campaignId + dateRange + groupby) so repeated
 * expands of the same row don't trigger extra network calls.
 */
export function useCampaignDates(
  campaignId: string | null,  // null = not yet expanded
  dateFrom: string,
  dateTo: string,
  groupby: GroupBy
) {
  const [dates, setDates] = useState<DateRow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const cache = useRef<Record<string, DateRow[]>>({});

  const cacheKey = `${campaignId}-${dateFrom}-${dateTo}-${groupby}`;

  useEffect(() => {
    if (!campaignId) return;

    if (cache.current[cacheKey]) {
      setDates(cache.current[cacheKey]);
      return;
    }

    let cancelled = false;
    setIsLoading(true);

    fetchCampaignDates(campaignId, dateFrom, dateTo, groupby)
      .then((res) => {
        if (cancelled) return;
        cache.current[cacheKey] = res.dates;
        setDates(res.dates);
      })
      .catch(() => {
        if (!cancelled) setDates([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => { cancelled = true; };
  }, [campaignId, cacheKey, dateFrom, dateTo, groupby]);

  return { dates, isLoading, cache: cache.current };
}

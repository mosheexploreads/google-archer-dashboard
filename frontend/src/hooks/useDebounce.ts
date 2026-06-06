import { useState, useEffect } from "react";

/**
 * Returns a debounced copy of `value` that only updates after `delayMs` of no
 * changes. Pass a memoized object so its identity is stable between renders.
 */
export function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}

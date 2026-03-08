import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import type { ProductWarning } from "../types";

export function useWarnings() {
  const [warnings, setWarnings] = useState<ProductWarning[]>([]);

  const load = useCallback(() => {
    axios
      .get<{ warnings: ProductWarning[] }>("/api/dashboard/warnings")
      .then((r) => setWarnings(r.data.warnings))
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { warnings, reload: load };
}

import { useCallback, useEffect, useRef, useState } from "react";

import { apiRequest } from "../../core/api";
import type { PluginHost } from "./types";

export function usePluginCatalog() {
  const [hosts, setHosts] = useState<PluginHost[] | null>(null);
  const [error, setError] = useState("");
  const mounted = useRef(false);
  const fetching = useRef(false);

  const load = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const result = await apiRequest<{ hosts: PluginHost[] }>("/plugins");
      if (mounted.current) {
        setHosts(result.hosts);
        setError("");
      }
    } catch (caught) {
      if (mounted.current)
        setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      fetching.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 3000);
    return () => {
      mounted.current = false;
      window.clearInterval(timer);
    };
  }, [load]);

  return { hosts, error, setError, load };
}

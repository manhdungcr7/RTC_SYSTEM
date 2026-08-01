import { useCallback, useState } from "react";

import * as api from "../services/api";
import type { SearchHit } from "../types/search";

export function useImageSearch() {
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runImageSearch = useCallback(async (file: File, topk = 100) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.similarSearchUpload(file, topk);
      setHits(res.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { hits, loading, error, runImageSearch };
}

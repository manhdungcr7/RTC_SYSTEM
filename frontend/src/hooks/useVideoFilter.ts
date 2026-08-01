import { useCallback, useState } from "react";

import * as api from "../services/api";
import type { VideoHit } from "../types/videos";

export function useVideoFilter() {
  const [hits, setHits] = useState<VideoHit[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runVideoSearch = useCallback(async (query: string, category: string | null, topk = 100) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchVideos({ query, category, topk });
      setHits(res.hits);
      setCategories(res.categories);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { hits, categories, loading, error, runVideoSearch };
}

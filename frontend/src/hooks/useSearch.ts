import { useCallback, useState } from "react";

import * as api from "../services/api";
import type { SearchHit, SearchRequest, SignalInfo } from "../types/search";

export function useSearch() {
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clausesMetaclip2, setClausesMetaclip2] = useState<string[]>([]);
  const [clausesEn, setClausesEn] = useState<string[]>([]);
  const [ocrKeywords, setOcrKeywords] = useState<string[]>([]);
  const [signalsUsed, setSignalsUsed] = useState<SignalInfo[]>([]);
  const [strictFilterApplied, setStrictFilterApplied] = useState(false);
  const [strictFilterPoolSize, setStrictFilterPoolSize] = useState<number | null>(null);

  const runSearch = useCallback(async (req: SearchRequest) => {
    if (!req.query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.search(req);
      setHits(res.hits);
      setClausesMetaclip2(res.clauses_metaclip2);
      setClausesEn(res.clauses_en);
      setOcrKeywords(res.ocr_keywords);
      setSignalsUsed(res.signals_used);
      setStrictFilterApplied(res.strict_filter_applied);
      setStrictFilterPoolSize(res.strict_filter_pool_size);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    hits, loading, error, clausesMetaclip2, clausesEn, ocrKeywords, signalsUsed,
    strictFilterApplied, strictFilterPoolSize, runSearch,
  };
}

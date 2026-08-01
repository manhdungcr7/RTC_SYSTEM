import { useCallback, useState } from "react";

import * as api from "../services/api";
import type { TemporalCandidate } from "../types/temporal";

export function useTemporal() {
  const [candidates, setCandidates] = useState<TemporalCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runTemporal = useCallback(async (
    events: string[],
    context: string,
    ocrQueries?: string[],
    asrQueries?: string[],
    lambdaPenalty?: number,
    anchorIndices?: number[],
  ) => {
    if (events.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.temporalSearch({
        events, context, topk: 50, per_event: 1500,
        ocr_queries: ocrQueries, asr_queries: asrQueries, lambda_penalty: lambdaPenalty,
        anchor_indices: anchorIndices,
      });
      setCandidates(res.candidates);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { candidates, loading, error, runTemporal };
}

/** Quy đổi trạng thái PHIÊN -> request /search, và chạy qua TanStack Query.
 *
 *  Cache theo TOÀN BỘ tham số: quay lại một truy vấn đã chạy là tức thì, không
 *  gọi lại máy chủ. Kết hợp với 2 tầng cache phía backend (vector + kết quả từng
 *  nhánh), việc chỉnh trọng số rồi tìm lại chỉ tốn vài chục ms — đây là điều
 *  kiện để bàn trộn tín hiệu dùng được thật trong lúc thi.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { api } from "../../api/client";
import type { SessionState } from "../../stores/sessionStore";
import { BRANCHES } from "../../types/api";
import type { SearchRequest, SearchResponse } from "../../types/api";

/** Chỉ gửi nhánh ĐANG BẬT kèm trọng số đang hiển thị — không có số nào vô hình. */
function buildSignals(s: SessionState): Record<string, { enabled: boolean; weight: number }> {
  const out: Record<string, { enabled: boolean; weight: number }> = {};
  for (const b of BRANCHES) {
    out[b.key] = { enabled: !!s.enabled[b.key], weight: s.weights[b.key] ?? 0 };
  }
  return out;
}

export function buildRequest(s: SessionState, opts?: { explain?: boolean; branchLists?: boolean }): SearchRequest {
  const req: SearchRequest = {
    query: s.query,
    kind: s.kind,
    topk: s.topk,
    use_expansion: true,
    split_clauses: s.autoSplit,
    signals: buildSignals(s),
    clause_fusion: { mode: "max_alpha_mean", alpha: s.alpha },
    fusion: { method: "rrf", k: s.rrfK },
    per_video_cap: s.perVideoCap,
    explain: opts?.explain ?? true,
    branch_lists: opts?.branchLists ?? true,
  };

  if (s.clausesDirty && s.clauses.length) req.clauses = s.clauses;
  if (s.translationsDirty && Object.keys(s.translations).length) req.translations = s.translations;
  if (s.dedupSeconds > 0) req.dedup_seconds = s.dedupSeconds;

  if (s.enabled.ocr && s.ocr.query.trim()) req.ocr = s.ocr;
  if (s.enabled.asr && s.asr.query.trim()) req.asr = s.asr;
  else if (s.enabled.asr_emb && s.asr.semantic) {
    // Khớp ý nghĩa lời thoại dùng chính câu truy vấn khi chưa gõ riêng ô ASR.
    req.asr = { ...s.asr, query: "", lexical: false, semantic: true };
  }
  if (s.enabled.object && s.objects.length) req.objects = s.objects;
  if (s.negative.text.trim()) {
    req.negative = {
      text: s.negative.text,
      weight: s.negative.weight,
      hard_threshold: s.negative.hardThreshold,
    };
  }
  if (s.scopeVideos.length) {
    req.scope = { video_ids: s.scopeVideos, invert: s.scopeInvert };
  }
  if (s.enabled.dinov3) {
    if (s.refImageB64) req.ref_image_b64 = s.refImageB64;
    else if (s.refVideo && s.refN != null) { req.ref_video = s.refVideo; req.ref_n = s.refN; }
  }
  if (s.feedbackPos.length || s.feedbackNeg.length) {
    req.feedback = {
      positive: s.feedbackPos, negative: s.feedbackNeg,
      beta: s.feedbackBeta, gamma: s.feedbackGamma,
    };
  }
  return req;
}

/** Bấm "Tìm" mới chụp lại tham số — tránh gõ tới đâu chạy tới đó (tốn GPU,
 *  và người dùng cần chủ động quyết định khi nào chạy). */
export function useSearchRunner() {
  const qc = useQueryClient();
  const [submitted, setSubmitted] = useState<SearchRequest | null>(null);

  const query = useQuery<SearchResponse>({
    queryKey: ["search", submitted],
    queryFn: ({ signal }) => api.search(submitted!, signal),
    enabled: submitted !== null,
    staleTime: 5 * 60_000,
    gcTime: 30 * 60_000,
    retry: 0,
  });

  const run = useCallback((req: SearchRequest) => setSubmitted(req), []);
  const clear = useCallback(() => setSubmitted(null), []);
  const invalidate = useCallback(
    () => qc.invalidateQueries({ queryKey: ["search"] }), [qc]);

  return {
    run, clear, invalidate,
    request: submitted,
    data: query.data,
    isLoading: query.isFetching,
    error: query.error as Error | null,
  };
}

/** Tách mệnh đề để hiển thị cho người dùng SỬA — chạy riêng, không đợi tìm kiếm. */
export function useClauseSuggest() {
  return useMutation({
    mutationFn: async (query: string) => {
      const res = await api.search({
        query, topk: 1, explain: false, branch_lists: false,
        signals: Object.fromEntries(BRANCHES.map((b) => [b.key, { enabled: false }])),
      });
      return { vi: res.clauses_metaclip2, en: res.clauses_en };
    },
  });
}

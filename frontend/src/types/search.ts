// Mirror của api/schemas/search.py — giữ đồng bộ tay khi backend đổi field.

export type QueryKind = "kis" | "qa" | "trake";

export interface SearchRequest {
  query: string;
  kind: QueryKind;
  topk?: number;
  use_expansion?: boolean;
  ocr_query?: string;
  asr_query?: string;
  object_query?: string;
}

export interface SearchHit {
  id: string;
  video: string;
  n: number;
  frame_idx: number;
  score: number;
  thumb_url: string;
  pts_time: number | null;
}

export interface SignalInfo {
  name: string;
  weight: number;
  query_text: string | null;
  n_hits: number;
}

export interface SearchResponse {
  hits: SearchHit[];
  clauses_metaclip2: string[];
  clauses_en: string[];
  ocr_keywords: string[];
  signals_used: SignalInfo[];
}

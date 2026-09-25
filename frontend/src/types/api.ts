// Bản sao TypeScript của api/schemas/*.py — giữ đồng bộ tay khi backend đổi.

export type QueryKind = "kis" | "qa" | "trake";
export type TextMode = "score" | "filter";

/** 4 nhánh dùng chung cho bàn trộn của cả Search lẫn Temporal. */
export const TEMPORAL_BRANCHES = ["metaclip2", "pecore", "beit3", "capemb"] as const;

/** 9 nhánh tín hiệu. Thứ tự ở đây LÀ thứ tự hiển thị trên bàn trộn. */
export const BRANCHES = [
  { key: "metaclip2", short: "MC2",  label: "MetaCLIP-2",     kind: "vector",
    hint: "Nhánh thị giác CHÍNH. Hiểu thẳng tiếng Việt, không cần dịch." },
  { key: "pecore",    short: "PE",   label: "PE-Core",        kind: "vector",
    hint: "Thị giác chi tiết. Chỉ hiểu tiếng Anh nên dùng bản dịch." },
  { key: "beit3",     short: "B3",   label: "BEiT-3",         kind: "vector",
    hint: "Bổ trợ, bắt chi tiết nhỏ và chữ trong ảnh. Dùng bản dịch." },
  { key: "capemb",    short: "CAP",  label: "Mô tả cảnh",     kind: "vector",
    hint: "So câu hỏi với mô tả cảnh đã sinh sẵn cho từng khung hình. Không giới hạn độ dài câu." },
  { key: "asr_emb",   short: "AEMB", label: "Lời thoại (ý)",  kind: "vector",
    hint: "Khớp Ý NGHĨA lời thoại — hỏi 'giá xăng tăng' vẫn ra đoạn nói 'giá nhiên liệu leo thang'." },
  { key: "dinov3",    short: "DINO", label: "Ảnh giống",      kind: "vector",
    hint: "Tìm khung hình giống ẢNH MẪU. Cần có ảnh tham chiếu mới chạy." },
  { key: "ocr",       short: "OCR",  label: "Chữ trên hình",  kind: "text",
    hint: "Chữ đọc được trong khung hình. Chỉ chạy khi bạn tự gõ." },
  { key: "asr",       short: "ASR",  label: "Lời thoại (từ)", kind: "text",
    hint: "Khớp ĐÚNG TỪ trong lời thoại. Chỉ chạy khi bạn tự gõ." },
  { key: "object",    short: "OBJ",  label: "Vật thể + màu",  kind: "text",
    hint: "Vật thể và màu sắc xuất hiện trong khung hình." },
] as const;

export type BranchKey = (typeof BRANCHES)[number]["key"];

export const BRANCH_COLOR: Record<string, string> = {
  metaclip2: "var(--color-sig-metaclip2)",
  pecore: "var(--color-sig-pecore)",
  beit3: "var(--color-sig-beit3)",
  dinov3: "var(--color-sig-dinov3)",
  capemb: "var(--color-sig-capemb)",
  asr_emb: "var(--color-sig-asr_emb)",
  ocr: "var(--color-sig-ocr)",
  asr: "var(--color-sig-asr)",
  object: "var(--color-sig-object)",
};

/** Trọng số khởi đầu. ĐÂY CHỈ LÀ ĐIỂM XUẤT PHÁT, không phải chân lý —
 *  người dùng chỉnh tay bất cứ lúc nào và giá trị luôn hiện rõ (P1). */
export const DEFAULT_WEIGHTS: Record<string, number> = {
  metaclip2: 1.0, pecore: 0.7, beit3: 0.4, capemb: 0.6,
  asr_emb: 0.35, dinov3: 0.5, ocr: 0.25, asr: 0.15, object: 0.6,
};

// ==================== Request ====================

export interface SignalConfig { enabled: boolean; weight?: number | null }
export interface ClauseConfig { text: string; weight: number; enabled: boolean }
/** 1 CƠ CHẾ DUY NHẤT: khớp đủ mọi từ đã gõ (thứ tự tự do), dung sai lỗi chính
 *  tả áp dụng tự động theo từng từ (cấp index, không cần người dùng chỉnh). */
export interface OcrConfig { query: string; mode: TextMode }
export interface AsrConfig {
  query: string; lexical: boolean; semantic: boolean;
  mode: TextMode; window_before: number; window_after: number;
}
/** Đã bỏ vị trí lưới 3x3 — ít tác dụng phân biệt, chỉ còn vật thể + màu. */
export interface ObjectCond { cls: string; color?: string | null; min_count: number }
export interface NegativeConfig { text: string; weight: number; hard_threshold?: number | null }
export interface FrameRef { video: string; n: number }
export interface FeedbackConfig {
  positive: FrameRef[]; negative: FrameRef[]; beta: number; gamma: number;
}
export interface VideoScopeConfig { video_ids: string[]; invert: boolean }
export interface FusionConfig { method: "rrf" | "weighted_sum"; k: number }

export interface SearchRequest {
  query: string;
  kind?: QueryKind;
  topk?: number;
  use_expansion?: boolean;
  split_clauses?: boolean;
  signals?: Record<string, SignalConfig>;
  clauses?: ClauseConfig[];
  clause_fusion?: { mode: "max_alpha_mean"; alpha: number };
  translations?: Record<number, string>;
  ocr?: OcrConfig;
  asr?: AsrConfig;
  objects?: ObjectCond[];
  negative?: NegativeConfig;
  feedback?: FeedbackConfig;
  scope?: VideoScopeConfig;
  fusion?: FusionConfig;
  per_video_cap?: number;
  dedup_seconds?: number;
  ref_video?: string;
  ref_n?: number;
  ref_image_b64?: string;
  explain?: boolean;
  branch_lists?: boolean;
}

// ==================== Response ====================

export interface BranchContribution {
  branch: string; rank: number; raw: number; weight: number; rrf: number;
}
export interface ClauseScore { text: string; score: number }
export interface FrameContent {
  caption?: string | null;
  ocr?: string | null;
  objects?: string | null;
  asr_window: { t: number; end: number; text: string }[];
}
export interface HitExplain {
  branches: BranchContribution[];
  clauses: ClauseScore[];
  penalties: Record<string, number>;
}
export interface SearchHit {
  id: string; video: string; n: number; frame_idx: number;
  score: number; thumb_url: string; pts_time: number | null; rank: number;
  explain?: HitExplain | null;
  content?: FrameContent | null;
}
export interface SignalInfo {
  name: string; weight: number; query_text: string | null; n_hits: number;
}
export interface BranchRanking { branch: string; hits: SearchHit[] }
export interface SearchResponse {
  hits: SearchHit[];
  clauses_metaclip2: string[];
  clauses_en: string[];
  ocr_keywords: string[];
  signals_used: SignalInfo[];
  strict_filter_applied: boolean;
  strict_filter_pool_size: number | null;
  total_candidates: number;
  took_ms: number;
  branch_rankings: BranchRanking[];
  cache_stats?: Record<string, unknown> | null;
}

// ==================== External GPT query plan ====================

export interface QueryPlanContext { vi: string; en: string }
export interface QueryPlanEvent {
  vi: string;
  en: string;
  anchor: boolean;
  visual_keywords: string[];
  ocr: string;
  asr: string;
}
export interface VisualQueryPlan {
  original_query: string;
  context: QueryPlanContext;
  events: QueryPlanEvent[];
  search_clauses: string[];
  search_clauses_en: string[];
  distinctive_features: string[];
  possible_confusions: string[];
  ocr_queries: string[];
  asr_queries: string[];
  recommended_mode: "search" | "temporal";
  max_gap_s: number | null;
}
export interface QueryPlanValidationResponse {
  plan: VisualQueryPlan;
  warnings: string[];
}

// ==================== Temporal ====================

export interface TemporalRequest {
  events: string[];
  context?: string;
  /** Bản dịch đã được GPT/người dùng xác nhận, song song 1:1 với events. */
  event_translations?: string[];
  topk?: number;
  per_event?: number;
  split_clauses?: boolean;
  ocr_queries?: string[];
  asr_queries?: string[];
  // ĐÃ BỎ lambda_penalty — Temporal LUÔN không phạt khoảng cách thời gian, xem
  // api/routers/temporal.py.
  signals?: Record<string, SignalConfig>;
  anchor_indices?: number[] | null;
  video_scope?: string[] | null;
  locked_frames?: (number | null)[] | null;
  gap_constraints?: { from: number; to: number; min_s?: number | null; max_s?: number | null }[];
  /** Giới hạn giây mặc định giữa hai sự kiện liền kề; null = không giới hạn. */
  max_gap_s?: number | null;
  alternates_per_event?: number;
  // Phản hồi liên quan RIÊNG từng sự kiện — key = chỉ số sự kiện (0-based).
  // Đánh dấu ✓/✗ trên khung của sự kiện nào chỉ dịch vector của đúng sự kiện đó.
  feedback?: Record<number, FeedbackConfig>;
  // Ghi đè tay mệnh đề đã tách CHO TỪNG sự kiện — key = chỉ số sự kiện, value =
  // danh sách câu tự viết, thay hẳn tách tự động cho ĐÚNG sự kiện đó.
  clauses_override?: Record<number, string[]>;
}
export interface TemporalEventHit extends SearchHit { alternates?: SearchHit[] }
export interface TemporalCandidate {
  video: string;
  total_score: number;
  hits: TemporalEventHit[];
  breakdown?: Record<string, number> | null;
}
export interface TemporalResponse {
  candidates: TemporalCandidate[];
  // Mệnh đề THỰC SỰ đã dùng để encode cho từng sự kiện, cùng thứ tự với events
  // gửi lên — event_clauses[i] == [events[i]] nghĩa là không tách thêm được.
  event_clauses?: string[][];
}

// ==================== Video / media ====================

export interface VideoHit {
  video: string; score: number;
  category: string | null; title: string | null; thumb_url: string;
}
export interface VideoSearchResponse { hits: VideoHit[]; categories: string[] }

export interface VideoMapRow { n: number; frame_idx: number; pts_time: number }
export interface VideoMap {
  video: string; fps: number; duration: number | null; rows: VideoMapRow[];
}

export interface DresEvaluation {
  id: string; name: string; status: string; type: string;
}
export interface DresCurrentTask { name: string; task_type: string }
export interface DresAnswer {
  kind: QueryKind;
  row: (string | number)[];
  n_events: number | null;
}
export interface DresPayload {
  answerSets: { answers: ({ mediaItemName: string; start: number; end: number } | { text: string })[] }[];
}

export interface HealthStatus {
  status: "ok" | "degraded";
  faiss?: { ok: boolean; branches: Record<string, number> };
  meili?: { ok: boolean; latency_ms?: number; docs?: Record<string, number | null>; error?: string };
  encoder?: { ok: boolean; url: string | null; latency_ms?: number; error?: string; note?: string };
  cache?: Record<string, { hits: number; misses: number; hit_rate: number }>;
}

// ==================== Bang chia se bai nop ====================

export type TeamCheckStatus = "unchecked" | "checked" | "needs_rework";

export interface LiveReveal {
  id: number;
  question_id: string;
  position: number;
  text_vi: string;
  text_en: string;
  created_at: string;
  updated_at: string;
}

export interface LiveQuestion {
  id: string;
  label: string;
  kind: QueryKind;
  qa_question: string;
  created_at: string;
  updated_at: string;
  reveals: LiveReveal[];
}

export interface TeamIdentity {
  displayName: string;
  memberId: string;
}

export interface TeamSharedAnswer {
  batch_id: string;
  question_number: number;
  member_id: string;
  display_name: string;
  csv_text: string;
  note: string;
  check_status: TeamCheckStatus;
  checked_by_member_id: string | null;
  checked_by_name: string | null;
  checked_at: string | null;
  updated_at: string;
}

export interface TeamQuestion {
  batch_id: string;
  number: number;
  filename: string;
  kind: QueryKind;
  description: string;
  trake_event_count: number | null;
  answers: TeamSharedAnswer[];
  selected_member_id: string | null;
  chosen_by_member_id?: string | null;
  chosen_by_name?: string | null;
  choice_updated_at?: string | null;
}

export interface TeamBatch {
  id: string;
  question_count: number;
  source_fingerprint: string;
  created_at: string;
  questions: TeamQuestion[];
}

export interface TeamBatchSummary {
  id: string;
  question_count: number;
  created_at: string;
}

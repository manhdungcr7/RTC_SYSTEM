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
  // Chọn tay nhánh model embedding nào chạy — undefined = mặc định cũ (bật hết).
  // UI mặc định chỉ tích metaclip2 (xem QueryBox.tsx).
  models?: string[];
  // Trọng số động (mục 2) — ghi đè tại chỗ, key = tên tín hiệu (xem SIGNAL_WEIGHT_KEYS).
  weights?: Record<string, number>;
  // DINOv3 tích hợp chung (mục 1) — 1 trong 2 nguồn ảnh tham chiếu.
  ref_video?: string;
  ref_n?: number;
  ref_image_b64?: string;
  // Lọc video trước (mục 3) — danh sách video giới hạn phạm vi tìm.
  video_scope?: string[];
  // Strict OCR/ASR filter (mục 4).
  strict_text_filter?: boolean;
}

export const MODEL_OPTIONS = [
  { key: "metaclip2", label: "MetaCLIP-2 (chính)" },
  { key: "beit3", label: "BEiT-3 (ensemble, lợi QA)" },
  { key: "pecore", label: "PE-Core (chi tiết)" },
  { key: "capemb", label: "Qwen3-Embedding (caption)" },
  { key: "asr_emb", label: "Qwen3-Embedding (ASR ngữ nghĩa)" },
  { key: "dinov3", label: "DINOv3 (ảnh tham chiếu)" },
] as const;

// Trọng số ĐỘNG (mục 2) — mọi tín hiệu tham gia RRF, không chỉ 5 model embedding
// (khác MODEL_OPTIONS ở trên — đó là BẬT/TẮT có chạy hay không, đây là CHỈNH
// TRỌNG SỐ khi ĐÃ chạy). Nhãn hiển thị giá trị mặc định ĐIỂN HÌNH (KIS) chỉ để
// tham khảo — backend có mặc định RIÊNG theo kind (kis/qa/trake), UI KHÔNG gửi
// key nào chưa được người dùng bật ghi đè (xem WeightPanel.tsx).
export const SIGNAL_WEIGHT_KEYS = [
  { key: "metaclip2", label: "MetaCLIP-2", typical: 1.0 },
  { key: "pecore", label: "PE-Core", typical: 0.3 },
  { key: "beit3", label: "BEiT-3", typical: 0.2 },
  { key: "capemb", label: "Qwen3-Embedding (caption)", typical: 0.5 },
  { key: "dinov3", label: "DINOv3 (ảnh tham chiếu)", typical: 0.5 },
  { key: "asr_emb", label: "ASR ngữ nghĩa", typical: 0.15 },
  { key: "ocr", label: "OCR (nguyên văn)", typical: 0.25 },
  { key: "ocr_keyword", label: "OCR (từ khoá riêng)", typical: 1.5 },
  { key: "asr", label: "ASR (khớp từ)", typical: 0.15 },
  { key: "object", label: "Object + màu", typical: 0.6 },
  { key: "entity", label: "Entity (LLM)", typical: 1.5 },
] as const;

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
  strict_filter_applied: boolean;
  strict_filter_pool_size: number | null;
}

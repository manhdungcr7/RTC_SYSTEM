import type { SearchHit } from "./search";

export interface TemporalRequest {
  events: string[];
  context?: string;
  topk?: number;
  per_event?: number;
  // Ghi đè tay OCR/ASR RIÊNG cho từng sự kiện (song song với `events`, cùng độ
  // dài, phần tử rỗng = dùng tự động theo câu event) — xem api/schemas/temporal.py.
  ocr_queries?: string[];
  asr_queries?: string[];
  // None/undefined = dùng TRAKE_LAMBDA mặc định. Đặt 0 khi các sự kiện KHÔNG
  // cần gần nhau về thời gian.
  lambda_penalty?: number;
  // 2 chỉ số sự kiện dùng làm NEO thị giác cho boundary-anchor — undefined =
  // mặc định (E1, En cuối). Đặt tay khi 1 cặp sự kiện Ở GIỮA dễ nhận diện thị
  // giác hơn đầu/cuối (vd query múa lân: E2/E3 đặc trưng hơn E1/E4).
  anchor_indices?: number[];
}

export interface TemporalCandidate {
  video: string;
  total_score: number;
  hits: SearchHit[];
}

export interface TemporalResponse {
  candidates: TemporalCandidate[];
}

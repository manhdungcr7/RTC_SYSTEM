/** Lớp gọi API duy nhất. Mọi request đi qua /api/* (Vite proxy khi dev, nginx
 *  khi chạy thật — xem docker/nginx.conf). Ảnh/video đi thẳng /media/*. */
import type {
  HealthStatus, SearchHit, SearchRequest, SearchResponse, TemporalRequest, TemporalResponse,
  TeamBatch, TeamBatchSummary, TeamCheckStatus, VideoMap, VideoSearchResponse,
} from "../types/api";

const API = "/api";

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(text || `Máy chủ trả lỗi ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API}${path}`, { signal });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(text || `Máy chủ trả lỗi ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), signal,
  });
  if (!res.ok) throw new ApiError(await res.text(), res.status);
  return res.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), signal,
  });
  if (!res.ok) throw new ApiError(await res.text(), res.status);
  return res.json() as Promise<T>;
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API}${path}`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(await res.text(), res.status);
  return res.json() as Promise<T>;
}

async function download(path: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) throw new ApiError(await res.text(), res.status);
  return res.blob();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!res.ok) throw new ApiError(await res.text(), res.status);
  return res.json() as Promise<T>;
}

export const api = {
  search: (req: SearchRequest, signal?: AbortSignal) =>
    post<SearchResponse>("/search", req, signal),

  temporal: (req: TemporalRequest, signal?: AbortSignal) =>
    post<TemporalResponse>("/temporal", req, signal),

  searchVideos: (query: string, category: string | null, topk = 100, field = "all",
                 signal?: AbortSignal) =>
    post<VideoSearchResponse>("/search/videos", { query, category, topk, field }, signal),

  videoMap: (video: string, signal?: AbortSignal) =>
    get<VideoMap>(`/videos/${encodeURIComponent(video)}/map`, signal),

  videoTranscript: (video: string, signal?: AbortSignal) =>
    get<{ video: string; segments: { t: number; end: number; text: string }[] }>(
      `/videos/${encodeURIComponent(video)}/transcript`, signal),

  videoOcr: (video: string, signal?: AbortSignal) =>
    get<{ video: string; rows: { n: number; text: string }[] }>(
      `/videos/${encodeURIComponent(video)}/ocr`, signal),

  videoKeyframes: (video: string, signal?: AbortSignal) =>
    get<{ video: string; frames: { n: number; frame_idx: number; pts_time: number }[] }>(
      `/videos/${encodeURIComponent(video)}/keyframes`, signal),

  health: (signal?: AbortSignal) => get<HealthStatus>("/health", signal),

  getEncoderConfig: () => get<{ url: string | null; has_key: boolean }>("/config/encoder"),
  setEncoderConfig: (url: string, key: string) =>
    post<{ ok: boolean; detail?: unknown; error?: string }>("/config/encoder", { url, key }),

  submitPreview: (kind: string, rows: unknown[][], n_events?: number | null) =>
    post<{ csv_text: string; errors: string[] }>("/submit/build",
      { kind, rows, n_events: n_events ?? null }),

  /** Tra tay 1 khung hình theo (video, frame_idx) — xem api/routers/media.py.
   *  Đi qua `/media/` (không phải `/api/`) — cùng cách thumbUrl/videoUrl gọi. */
  lookupFrame: async (video: string, frameIdx: number, signal?: AbortSignal): Promise<SearchHit> => {
    const res = await fetch(
      `/media/lookup/${encodeURIComponent(video)}?frame_idx=${encodeURIComponent(frameIdx)}`,
      { signal });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new ApiError(text || `Máy chủ trả lỗi ${res.status}`, res.status);
    }
    return res.json();
  },

  submitPack: async (files: Record<string, string>): Promise<Blob> => {
    const res = await fetch(`${API}/submit/pack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    if (!res.ok) throw new ApiError(await res.text(), res.status);
    return res.blob();
  },

  listTeamBatches: (signal?: AbortSignal) => get<TeamBatchSummary[]>("/team-submissions/batches", signal),
  getTeamBatch: (batchId: string, signal?: AbortSignal) =>
    get<TeamBatch>(`/team-submissions/batches/${encodeURIComponent(batchId)}`, signal),
  deleteTeamBatch: (batchId: string) =>
    del<{ id: string; question_count: number; deleted: true }>(`/team-submissions/batches/${encodeURIComponent(batchId)}`),
  importQuestions: (file: File, replaceExisting = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("replace_existing", String(replaceExisting));
    return postForm<{ imported: boolean; batch: TeamBatch }>("/team-submissions/batches/import-questions", form);
  },
  shareTeamAnswer: (batchId: string, questionNumber: number, memberId: string,
                    data: { display_name: string; csv_text: string; note: string }) =>
    put(`/team-submissions/batches/${encodeURIComponent(batchId)}/questions/${questionNumber}/answers/${encodeURIComponent(memberId)}`, data),
  updateTeamAnswer: (batchId: string, questionNumber: number, memberId: string,
                     data: { actor_member_id: string; actor_display_name: string;
                             note?: string; check_status?: TeamCheckStatus }) =>
    patch(`/team-submissions/batches/${encodeURIComponent(batchId)}/questions/${questionNumber}/answers/${encodeURIComponent(memberId)}`, data),
  deleteTeamAnswer: (batchId: string, questionNumber: number, memberId: string) =>
    del<{ batch_id: string; question_number: number; member_id: string; deleted: true }>(
      `/team-submissions/batches/${encodeURIComponent(batchId)}/questions/${questionNumber}/answers/${encodeURIComponent(memberId)}`,
    ),
  chooseTeamAnswer: (batchId: string, questionNumber: number,
                     data: { member_id: string; actor_member_id: string; actor_display_name: string }) =>
    put(`/team-submissions/batches/${encodeURIComponent(batchId)}/questions/${questionNumber}/choice`, data),
  clearTeamChoice: (batchId: string, questionNumber: number) =>
    del<{ question_number: number; cleared: boolean }>(
      `/team-submissions/batches/${encodeURIComponent(batchId)}/questions/${questionNumber}/choice`,
    ),
  teamBackup: (batchId: string) => download(`/team-submissions/batches/${encodeURIComponent(batchId)}/backup`),
  restoreTeamBackup: (file: File, replaceExisting = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("replace_existing", String(replaceExisting));
    return postForm<{ batch: TeamBatch }>("/team-submissions/restore", form);
  },
  exportTeamSubmission: (batchId: string) =>
    download(`/team-submissions/batches/${encodeURIComponent(batchId)}/export`, { method: "POST" }),
};

/** Ảnh nhỏ cho lưới kết quả (bản 320px tiền sinh — nhẹ hơn ~40%). */
export const thumbUrl = (video: string, n: number) => `/media/thumb/${video}/${n}`;
/** Ảnh gốc — dùng ở khung xem chi tiết / so sánh, nơi cần nhìn rõ chi tiết. */
export const frameUrl = (video: string, n: number) => `/media/frame/${video}/${n}`;
export const videoUrl = (video: string) => `/media/video/${video}`;
/** Trích khung hình bất kỳ theo GIÂY (không phụ thuộc keyframe thưa). */
export const frameAtUrl = (video: string, t: number) =>
  `/media/frame_at/${video}?t=${t.toFixed(3)}`;

export { ApiError };

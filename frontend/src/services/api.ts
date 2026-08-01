import type { SearchRequest, SearchResponse } from "../types/search";
import type { SimilarRequest, SimilarResponse } from "../types/similar";
import type { TemporalRequest, TemporalResponse } from "../types/temporal";
import type { VideoSearchRequest, VideoSearchResponse } from "../types/videos";

async function postJson<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} -> ${res.status}: ${text}`);
  }
  return res.json() as Promise<TRes>;
}

export function search(req: SearchRequest): Promise<SearchResponse> {
  return postJson("/api/search", req);
}

export function temporalSearch(req: TemporalRequest): Promise<TemporalResponse> {
  return postJson("/api/temporal", req);
}

export function similarSearch(req: SimilarRequest): Promise<SimilarResponse> {
  return postJson("/api/similar", req);
}

// Lọc video trước (mục 3) — độc lập với /search khung hình.
export function searchVideos(req: VideoSearchRequest): Promise<VideoSearchResponse> {
  return postJson("/api/search/videos", req);
}

// Tìm ảnh giống từ 1 ảnh UPLOAD ngoài (chưa có sẵn trong index) — khác
// similarSearch() ở trên (dùng cho ảnh ĐÃ CÓ trong kết quả). multipart/form-data
// vì file ảnh, không phải JSON. Cần REMOTE encoder (DINOv3) đang chạy phía backend.
export async function similarSearchUpload(file: File, topk = 100): Promise<SimilarResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/similar/upload?topk=${topk}`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`/api/similar/upload -> ${res.status}: ${text}`);
  }
  return res.json() as Promise<SimilarResponse>;
}

export function frameUrl(video: string, n: number): string {
  return `/media/frame/${video}/${n}`;
}

export function videoUrl(video: string): string {
  return `/media/video/${video}`;
}

export function filmstripUrl(video: string, around: number, window = 10): string {
  return `/media/filmstrip/${video}?around=${around}&window=${window}`;
}

import type { SearchRequest, SearchResponse } from "../types/search";
import type { SimilarRequest, SimilarResponse } from "../types/similar";
import type { TemporalRequest, TemporalResponse } from "../types/temporal";

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

export function frameUrl(video: string, n: number): string {
  return `/media/frame/${video}/${n}`;
}

export function videoUrl(video: string): string {
  return `/media/video/${video}`;
}

export function filmstripUrl(video: string, around: number, window = 10): string {
  return `/media/filmstrip/${video}?around=${around}&window=${window}`;
}

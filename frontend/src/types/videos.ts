// Mirror của api/schemas/videos.py — lọc video trước (mục 3).

export interface VideoSearchRequest {
  query: string;
  category?: string | null;
  topk?: number;
}

export interface VideoHit {
  video: string;
  score: number;
  category: string;
  title: string;
  thumb_url: string;
}

export interface VideoSearchResponse {
  hits: VideoHit[];
  categories: string[];
}

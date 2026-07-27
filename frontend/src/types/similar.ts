import type { SearchHit } from "./search";

export interface SimilarRequest {
  video: string;
  n: number;
  topk?: number;
}

export interface SimilarResponse {
  hits: SearchHit[];
}

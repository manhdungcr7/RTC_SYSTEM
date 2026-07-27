import type { SearchHit } from "./search";

export interface TemporalRequest {
  events: string[];
  context?: string;
  topk?: number;
  per_event?: number;
}

export interface TemporalCandidate {
  video: string;
  total_score: number;
  hits: SearchHit[];
}

export interface TemporalResponse {
  candidates: TemporalCandidate[];
}

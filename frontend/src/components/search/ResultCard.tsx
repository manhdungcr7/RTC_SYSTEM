import type { SearchHit } from "../../types/search";

interface Props {
  hit: SearchHit;
  rank: number;
  onSelect: (hit: SearchHit) => void;
}

export function ResultCard({ hit, rank, onSelect }: Props) {
  return (
    <button className="result-card" onClick={() => onSelect(hit)} title={`${hit.video}:${hit.n}`}>
      <span className="result-card-rank">{rank}</span>
      <img src={hit.thumb_url} alt={`${hit.video} frame ${hit.n}`} loading="lazy" />
      <span className="result-card-video">{hit.video}</span>
    </button>
  );
}

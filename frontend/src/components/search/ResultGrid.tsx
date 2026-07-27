import type { SearchHit } from "../../types/search";
import { ResultCard } from "./ResultCard";

interface Props {
  hits: SearchHit[];
  onSelect: (hit: SearchHit) => void;
}

export function ResultGrid({ hits, onSelect }: Props) {
  if (hits.length === 0) {
    return <div className="result-grid-empty">Chưa có kết quả — nhập query rồi tìm kiếm.</div>;
  }
  return (
    <div className="result-grid">
      {hits.map((hit, i) => (
        <ResultCard key={hit.id} hit={hit} rank={i + 1} onSelect={onSelect} />
      ))}
    </div>
  );
}

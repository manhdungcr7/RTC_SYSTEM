import { useState } from "react";

import { EventTimeline } from "../components/temporal/EventTimeline";
import { TemporalResultCard } from "../components/temporal/TemporalResultCard";
import { FrameDetailModal } from "../components/search/FrameDetailModal";
import { useTemporal } from "../hooks/useTemporal";
import type { SearchHit } from "../types/search";

export function TemporalPage() {
  const { candidates, loading, error, runTemporal } = useTemporal();
  const [selected, setSelected] = useState<SearchHit | null>(null);

  const onSelectFrame = (video: string, n: number) => {
    const cand = candidates.find((c) => c.video === video);
    const hit = cand?.hits.find((h) => h.n === n);
    if (hit) setSelected(hit);
  };

  return (
    <div className="temporal-page">
      <EventTimeline onSearch={runTemporal} loading={loading} />
      {error && <div className="search-error">Lỗi: {error}</div>}
      <div className="temporal-results">
        {candidates.map((c, i) => (
          <TemporalResultCard key={`${c.video}-${i}`} candidate={c} rank={i + 1} onSelectFrame={onSelectFrame} />
        ))}
        {!loading && candidates.length === 0 && (
          <div className="result-grid-empty">Nhập ít nhất 2 sự kiện (E1, E2, ...) rồi tìm.</div>
        )}
      </div>
      {selected && <FrameDetailModal hit={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

import * as api from "../../services/api";
import type { TemporalCandidate } from "../../types/temporal";

interface Props {
  candidate: TemporalCandidate;
  rank: number;
  onSelectFrame: (video: string, n: number) => void;
}

export function TemporalResultCard({ candidate, rank, onSelectFrame }: Props) {
  return (
    <div className="temporal-candidate">
      <div className="temporal-candidate-header">
        <span>#{rank} {candidate.video}</span>
        <span className="temporal-score">score {candidate.total_score.toFixed(3)}</span>
      </div>
      <div className="temporal-sequence">
        {candidate.hits.map((h, i) => (
          <div key={h.id} className="temporal-frame" onClick={() => onSelectFrame(h.video, h.n)}>
            <span className="temporal-frame-label">E{i + 1}</span>
            <img src={api.frameUrl(h.video, h.n)} alt={`E${i + 1}`} />
          </div>
        ))}
      </div>
    </div>
  );
}

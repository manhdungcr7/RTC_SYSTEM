import { useState } from "react";

import * as api from "../../services/api";
import { useSubmissionStore } from "../../services/submission";
import type { SearchHit } from "../../types/search";
import { FilmstripPanel } from "./FilmstripPanel";

interface Props {
  hit: SearchHit;
  onClose: () => void;
}

export function FrameDetailModal({ hit: initialHit, onClose }: Props) {
  const [activeHit, setActiveHit] = useState(initialHit);
  const [currentN, setCurrentN] = useState(initialHit.n);
  const { activeFile, activeKind, addRow } = useSubmissionStore();
  const [similarHits, setSimilarHits] = useState<SearchHit[] | null>(null);
  const [similarLoading, setSimilarLoading] = useState(false);

  const currentThumb = api.frameUrl(activeHit.video, currentN);
  const videoSrc = activeHit.pts_time != null
    ? `${api.videoUrl(activeHit.video)}#t=${activeHit.pts_time}`
    : api.videoUrl(activeHit.video);

  const findSimilar = async () => {
    setSimilarLoading(true);
    setSimilarHits(null);
    try {
      const res = await api.similarSearch({ video: activeHit.video, n: currentN, topk: 20 });
      setSimilarHits(res.hits);
    } catch {
      setSimilarHits([]);
    } finally {
      setSimilarLoading(false);
    }
  };

  const jumpTo = (h: SearchHit) => {
    setActiveHit(h);
    setCurrentN(h.n);
    setSimilarHits(null);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>×</button>
        <h3>{activeHit.video} — frame {currentN} (frame_idx {activeHit.frame_idx})</h3>
        <div className="modal-body">
          <img className="modal-frame" src={currentThumb} alt={`${activeHit.video} frame ${currentN}`} />
          <video className="modal-video" src={videoSrc} controls />
        </div>
        <FilmstripPanel video={activeHit.video} around={activeHit.n} selectedN={currentN} onSelect={setCurrentN} />
        <div className="modal-actions">
          <span>Thêm vào <code>{activeFile}.csv</code> ({activeKind}):</span>
          <button onClick={() => addRow(activeFile, activeKind, { video: activeHit.video, frame_idx: activeHit.frame_idx })}>
            + Thêm frame này
          </button>
          <button onClick={findSimilar} disabled={similarLoading}>
            {similarLoading ? "Đang tìm..." : "🔍 Tìm ảnh giống"}
          </button>
        </div>
        {similarHits && (
          <div className="similar-grid">
            {similarHits.length === 0 ? (
              <div className="result-grid-empty">Không tìm được ảnh giống (nhánh dinov3 có thể đang tắt).</div>
            ) : (
              similarHits.map((h) => (
                <img
                  key={h.id}
                  src={h.thumb_url}
                  className="similar-grid-item"
                  title={`${h.video}:${h.n} (score ${h.score.toFixed(3)})`}
                  onClick={() => jumpTo(h)}
                  alt={`${h.video} frame ${h.n}`}
                />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

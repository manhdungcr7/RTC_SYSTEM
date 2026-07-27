"""TRAKE: tìm chuỗi sự kiện E1..En THEO ĐÚNG THỨ TỰ trong CÙNG một video. Port từ
`system/aic/engine.py:search_temporal` (boundary-anchor + DANTE DP) — DP loop giữ
NGUYÊN VẸN (toán cục bộ trong 1 video), chỉ thay nguồn dữ liệu: hệ cũ slice từ ma
trận toàn cục trong RAM, ở đây gọi `milvus_repo.fetch_video_vectors()` lấy vector
của TỪNG video ứng viên (nhẹ, ~100-300 keyframe/video) rồi nhân cục bộ.

THÊM (phát hiện qua test thật — xem hội thoại): chỉ dùng thị giác (metaclip2) KHÔNG
đủ phân biệt các cảnh nhìn GIỐNG NHAU (vd "cắt nấm" vs "cắt đậu hủ" — đều là cận
cảnh tay+dao+thớt). `/search` (KIS/QA) đã có OCR/ASR nhưng `/temporal` thì chưa —
giờ thêm OCR/ASR làm ĐIỂM CỘNG THÊM (không thay thế) vào từng ô của ma trận DP,
theo ĐÚNG câu chữ của từng sự kiện (event j chỉ được cộng điểm từ OCR/ASR khớp
CÂU CỦA event j, không phải câu của event khác).
"""
from __future__ import annotations

import numpy as np

from core import config as C
from core.fusion import Hit
from core.media_index import MediaIndex
from core.repositories.es_repo import EsRepo
from core.repositories.milvus_repo import MilvusRepo

ASR_ALIGN_WINDOW_S = 2.0


def _normalize01(scores: dict) -> dict:
    """Min-max về [0,1] — điểm BM25 KHÔNG cùng thang với cosine similarity (có thể
    là số bất kỳ >0 tuỳ tần suất từ), phải chuẩn hoá trước khi CỘNG vào ma trận DP
    (nếu không, 1 khớp OCR mạnh có thể áp đảo toàn bộ tín hiệu thị giác)."""
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _text_bonus_matrix(es_repo: EsRepo, media_index: MediaIndex, video: str,
                        ids: list[str], ns: list[int], event_texts: list[str],
                        per_video_size: int = 200) -> np.ndarray:
    """(n_ev, n_kf) điểm cộng OCR+ASR đã chuẩn hoá, CÙNG THỨ TỰ với `ids`/`ns` (đã
    sort theo n tăng dần — xem milvus_repo.fetch_video_vectors). Video không tồn
    tại trong ES / câu event rỗng -> hàng 0 (không cộng, không trừ — bỏ qua êm)."""
    n_ev, n_kf = len(event_texts), len(ids)
    bonus = np.zeros((n_ev, n_kf), dtype=np.float64)
    n_to_idx = {n: i for i, n in enumerate(ns)}
    ns_pts = media_index.video_ns_pts(video)   # [(n, pts_time), ...] sort theo n

    for j, text in enumerate(event_texts):
        if not text.strip():
            continue
        ocr_hits = _normalize01(es_repo.search_frames_scored("ocr_text", text, video, per_video_size))
        for doc_id, score in ocr_hits.items():
            n = int(doc_id.rsplit(":", 1)[-1])
            if n in n_to_idx:
                bonus[j, n_to_idx[n]] += C.OCR_WEIGHT.get("trake", 0.25) * score

        asr_segs = es_repo.search_asr_in_video(video, text, per_video_size)
        if asr_segs:
            raw = {i: s for i, (_, _, s) in enumerate(asr_segs)}
            norm = _normalize01(raw)
            for n, pts in ns_pts:
                if n not in n_to_idx:
                    continue
                best = 0.0
                for i, (start, end, _) in enumerate(asr_segs):
                    if start - ASR_ALIGN_WINDOW_S <= pts <= end + ASR_ALIGN_WINDOW_S:
                        best = max(best, norm[i])
                if best > 0:
                    bonus[j, n_to_idx[n]] += C.ASR_WEIGHT.get("trake", 0.15) * best
    return bonus


def search_temporal(event_vecs: np.ndarray, milvus_repo: MilvusRepo, collection: str,
                     per_event: int = 1500, topk: int = 100,
                     event_texts: list[str] | None = None,
                     es_repo: EsRepo | None = None,
                     media_index: MediaIndex | None = None) -> list[tuple[float, list[Hit]]]:
    """event_vecs: (n_ev, D) đã encode sẵn (1 vector/sự kiện, thường metaclip2).
    `event_texts`+`es_repo`+`media_index`: TÙY CHỌN — truyền đủ cả 3 thì cộng thêm
    tín hiệu OCR/ASR vào DP (khuyến nghị, xem docstring module). Thiếu 1 trong 3
    -> chỉ chạy thị giác thuần (giữ tương thích ngược, không lỗi).
    Trả list (total_score, hits) — hits = list n_ev Hit (1 hit/sự kiện, đúng thứ
    tự E1..En), sort theo total_score giảm dần."""
    n_ev = event_vecs.shape[0]
    if n_ev == 0:
        return []
    use_text = event_texts is not None and es_repo is not None and media_index is not None

    # --- Neo boundary: video có cả E1 và En trong top-per_event (MADTempo) ---
    # videos_from_topk() GIỮ THỨ TỰ rank -> cắt về MAX_TRAKE_CANDIDATES vẫn ưu tiên
    # đúng video liên quan nhất, không cắt ngẫu nhiên (xem lý do trong core.config).
    v_first = milvus_repo.videos_from_topk(collection, event_vecs[0], per_event)
    v_last = milvus_repo.videos_from_topk(collection, event_vecs[-1], per_event) if n_ev >= 2 else []
    set_first, set_last = set(v_first), set(v_last)
    inter = set_first & set_last
    if len(inter) >= 20:
        cand_videos = [v for v in v_first if v in inter]
    else:
        cand_videos = list(dict.fromkeys(v_first + v_last))
    cand_videos = cand_videos[:C.MAX_TRAKE_CANDIDATES]

    lam = C.TRAKE_LAMBDA
    results = []
    for video in cand_videos:
        ids, ns, frame_idxs, vecs = milvus_repo.fetch_video_vectors(collection, video)
        n_kf = len(ids)
        if n_kf < n_ev:
            continue
        sub = event_vecs @ vecs.T                          # (n_ev, n_kf)
        if use_text:
            sub = sub + _text_bonus_matrix(es_repo, media_index, video, ids, ns, event_texts)

        # DP: best[j][t] = điểm tốt nhất khi sự kiện j khớp keyframe t, chuỗi tăng
        # dần theo thời gian. DANTE: phạt khoảng cách λ(t-τ). Port nguyên engine.py:355-380.
        best = np.full((n_ev, n_kf), -np.inf, dtype=np.float64)
        back = np.zeros((n_ev, n_kf), dtype=np.int32)
        best[0] = sub[0]
        for j in range(1, n_ev):
            run_val, run_arg = -np.inf, -1
            for t in range(n_kf):
                if t > 0:
                    cand = best[j - 1, t - 1] + lam * (t - 1)
                    if cand > run_val:
                        run_val, run_arg = cand, t - 1
                if run_arg >= 0:
                    best[j, t] = sub[j, t] + run_val - lam * t
                    back[j, t] = run_arg

        t_end = int(np.argmax(best[-1]))
        if not np.isfinite(best[-1, t_end]):
            continue

        path = [t_end]
        for j in range(n_ev - 1, 0, -1):
            path.append(int(back[j, path[-1]]))
        path.reverse()

        total = float(best[-1, t_end]) / n_ev
        hits = [Hit(id=ids[t], video=video, n=ns[t], frame_idx=frame_idxs[t], score=float(sub[j, t]))
                for j, t in enumerate(path)]
        results.append((total, hits))

    results.sort(key=lambda x: -x[0])
    return results[:topk]

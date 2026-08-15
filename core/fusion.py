"""Hợp nhất đa tín hiệu. Port từ `system/aic/engine.py` — xem plan mục "Điều
chỉnh kiến trúc: từ FAISS-in-RAM sang Milvus/ES" cho lý do từng hàm khác bản gốc.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core import config as C
from core.repositories.faiss_repo import FaissRepo


@dataclass
class Hit:
    id: str
    video: str
    n: int
    frame_idx: int
    score: float


def rocchio(base_vec: np.ndarray, branch: str, faiss: FaissRepo,
            positive, negative, beta: float, gamma: float) -> np.ndarray:
    """Dịch chuyển vector truy vấn theo phản hồi ✓/✗ của người dùng:
        q' = q + beta*mean(vector các khung ✓) - gamma*mean(vector các khung ✗)
    Chạy HOÀN TOÀN trong RAM trên FAISS (index.reconstruct), KHÔNG gọi GPU — nên
    thao tác này tức thì. Đây là lợi thế trực tiếp của kiến trúc IndexFlatIP:
    vector gốc luôn lấy lại được, không như index nén/ANN.

    Con người rất giỏi nhận ra "cái này gần đúng, cái kia sai" dù không diễn đạt
    được bằng lời — Rocchio biến khả năng đó thành tín hiệu tìm kiếm. Dùng chung
    cho cả /search VÀ /temporal (mỗi sự kiện TRAKE tự dịch vector riêng của nó
    theo phản hồi CỦA ĐÚNG sự kiện đó) — CHỈ đổi vector đầu vào trước khi đưa vào
    fusion/DP, không đụng thuật toán phía sau ở cả 2 nơi dùng."""
    if not faiss.has_branch(branch):
        return base_vec

    def _mean(refs):
        vecs = []
        for r in refs:
            v = faiss.fetch_vector_by_id(branch, f"{r.video}:{r.n:06d}")
            if v is not None:
                vecs.append(v)
        return np.mean(np.stack(vecs), axis=0) if vecs else None

    q = np.asarray(base_vec, dtype=np.float32).copy()
    pos = _mean(positive) if positive else None
    neg = _mean(negative) if negative else None
    if pos is not None:
        q = q + beta * pos
    if neg is not None:
        q = q - gamma * neg
    n = np.linalg.norm(q)
    return (q / n).astype(np.float32) if n > 1e-8 else np.asarray(base_vec, dtype=np.float32)


def rrf(rank_lists: list[list[str]], k: int = C.RRF_K,
        weights: list[float] | None = None) -> dict[str, float]:
    """Reciprocal Rank Fusion — port NGUYÊN từ engine.py:59. Nhận thẳng rank-list id
    (Milvus/ES search() đều trả về đã sort) — không cần ma trận điểm toàn cục, đây
    là hàm fusion DUY NHẤT cần cho mọi nhánh (đơn giản hơn hệ cũ nhờ chuyển sang DB)."""
    if weights is None:
        weights = [1.0] * len(rank_lists)
    out: dict[str, float] = {}
    for w, ranks in zip(weights, rank_lists):
        for r, doc_id in enumerate(ranks):
            out[doc_id] = out.get(doc_id, 0.0) + w / (k + r + 1)
    return out


def maxmean_clauses(clause_vecs: np.ndarray, faiss_repo: FaissRepo, collection: str,
                     topk: int = C.MAXMEAN_TOPK_PER_CLAUSE,
                     alpha: float = C.MAXMEAN_ALPHA,
                     allowed_ids=None) -> list[tuple[str, float]]:
    """maxmean đa mệnh đề CỦA CÙNG 1 query, trên 1 collection (thường: metaclip2).

    Hệ cũ có ma trận đầy đủ trong RAM nên tính max/mean trên TOÀN BỘ N keyframe.
    Ở đây mỗi mệnh đề chỉ có top-`topk` (Milvus search) — hợp union các id xuất hiện
    ở BẤT KỲ mệnh đề nào thành candidate pool, rồi tính max+alpha*mean CHỈ trên các
    mệnh đề mà id đó THẬT SỰ xuất hiện (không gán 0 cứng cho id vắng mặt — ngoài
    top-800/167,850 gần như chắc chắn không phải ứng viên tốt, đánh đổi chấp nhận được).

    score = max_c cos(c,kf) + alpha * mean_c cos(c,kf) — công thức port nguyên
    (engine.py:216), đã đo thắng RRF/MAX/MEAN thuần trên benchmark manual.

    `allowed_ids`: TÙY CHỌN — khi có (video_scope mục 3, hoặc strict OCR/ASR
    filter mục 4), search CHÍNH XÁC (search_within_ids) chỉ trong tập này thay vì
    search gần đúng toàn kho — đúng đắn hơn khi tập đã lọc còn nhỏ."""
    if clause_vecs.shape[0] == 0:
        return []
    if allowed_ids is not None:
        rows = [faiss_repo.search_within_ids(collection, vec, allowed_ids, topk) for vec in clause_vecs]
    else:
        rows = faiss_repo.search_many_scored(collection, clause_vecs, topk)
    per_id: dict[str, list[float]] = {}
    for row in rows:
        for doc_id, dist in row:
            per_id.setdefault(doc_id, []).append(dist)

    scored = []
    for doc_id, sims in per_id.items():
        arr = np.array(sims)
        scored.append((doc_id, float(arr.max() + alpha * arr.mean())))
    scored.sort(key=lambda x: -x[1])
    return scored


def maxmean_clauses_detailed(clause_vecs: np.ndarray, faiss_repo: FaissRepo, collection: str,
                              topk: int = C.MAXMEAN_TOPK_PER_CLAUSE,
                              alpha: float = C.MAXMEAN_ALPHA,
                              allowed_ids=None,
                              clause_weights: list[float] | None = None,
                              ) -> tuple[list[tuple[str, float]], dict[str, list[float]]]:
    """Như maxmean_clauses() nhưng TRẢ THÊM điểm của TỪNG MỆNH ĐỀ cho từng khung
    hình — đây là nguồn dữ liệu cho dòng "Theo mệnh đề" trong bảng Vì sao (P3),
    công cụ chẩn đoán quan trọng nhất: thấy mệnh đề nào yếu thì biết ngay nên
    viết lại mệnh đề đó hay hạ trọng số nó, thay vì chỉ biết "kết quả sai".

    `clause_weights`: trọng số RIÊNG từng mệnh đề (người dùng chỉnh trong
    ClauseEditor) — nhân vào điểm cosine TRƯỚC khi lấy max/mean. None = đều 1.0.

    Trả (scored_sorted, per_clause) với per_clause[id] = [điểm mệnh đề 0, 1, ...]
    (NaN ở mệnh đề mà khung hình đó không lọt top-`topk` — phân biệt rõ "không
    xuất hiện" với "điểm 0", xem lý do trong maxmean_clauses)."""
    n_clauses = clause_vecs.shape[0]
    if n_clauses == 0:
        return [], {}
    if allowed_ids is not None:
        rows = [faiss_repo.search_within_ids(collection, vec, allowed_ids, topk) for vec in clause_vecs]
    else:
        rows = faiss_repo.search_many_scored(collection, clause_vecs, topk)

    weights = clause_weights if clause_weights else [1.0] * n_clauses
    per_clause: dict[str, list[float]] = {}
    for ci, row in enumerate(rows):
        w = weights[ci] if ci < len(weights) else 1.0
        for doc_id, dist in row:
            arr = per_clause.get(doc_id)
            if arr is None:
                arr = [float("nan")] * n_clauses
                per_clause[doc_id] = arr
            arr[ci] = float(dist) * w

    scored = []
    for doc_id, arr in per_clause.items():
        present = [v for v in arr if v == v]      # loại NaN (v != v chỉ đúng với NaN)
        if not present:
            continue
        a = np.array(present)
        scored.append((doc_id, float(a.max() + alpha * a.mean())))
    scored.sort(key=lambda x: -x[1])
    return scored, per_clause


def fuse_with_explain(signals: list[tuple[str, list[tuple[str, float]], float]],
                       k: int = C.RRF_K, method: str = "rrf",
                       ) -> tuple[dict[str, float], dict[str, list[dict]]]:
    """Gộp đa tín hiệu VÀ giữ lại phân rã đóng góp của từng nhánh cho từng khung
    hình — thay `rrf()` khi cần minh bạch (P3). `signals`: list
    (tên_nhánh, [(id, điểm_thô) đã sort giảm dần], trọng_số).

    method="rrf": đóng góp = w/(k+rank+1) — KHÔNG phụ thuộc thang điểm thô nên
    trộn được cosine với _rankingScore của Meilisearch (đây là lý do RRF là mặc
    định). method="weighted_sum": đóng góp = w * điểm_thô đã chuẩn hoá min-max
    TRONG TỪNG NHÁNH (so sánh chéo nhánh chỉ có nghĩa sau khi chuẩn hoá).

    Trả (điểm_gộp, phân_rã) với phân_rã[id] = [{branch, rank, raw, weight, rrf}]."""
    fused: dict[str, float] = {}
    detail: dict[str, list[dict]] = {}

    for branch, scored, w in signals:
        if not scored:
            continue
        if method == "weighted_sum":
            raws = [s for _, s in scored]
            lo, hi = min(raws), max(raws)
            span = (hi - lo) if (hi - lo) > 1e-9 else 1.0
        for rank0, (doc_id, raw) in enumerate(scored):
            if method == "weighted_sum":
                contrib = w * ((raw - lo) / span)
            else:
                contrib = w / (k + rank0 + 1)
            fused[doc_id] = fused.get(doc_id, 0.0) + contrib
            detail.setdefault(doc_id, []).append({
                "branch": branch, "rank": rank0 + 1, "raw": float(raw),
                "weight": float(w), "rrf": float(contrib),
            })
    return fused, detail


def dedup_by_time(hits: list[Hit], pts_of, window_s: float) -> list[Hit]:
    """Gộp các khung hình CÙNG VIDEO cách nhau < window_s giây làm một (giữ khung
    điểm cao nhất) — khác dedup_by_video (giới hạn theo SỐ LƯỢNG): ở đây mục tiêu
    là bỏ các khung gần như trùng nhau về nội dung do nằm sát nhau về thời gian,
    trả lại chỗ trong trang kết quả cho cảnh THẬT SỰ khác.

    `pts_of(video, n) -> float|None` — thiếu pts_time thì giữ nguyên khung đó
    (không đoán, không loại nhầm)."""
    if window_s <= 0:
        return hits
    kept_by_video: dict[str, list[float]] = {}
    out: list[Hit] = []
    for h in hits:                      # hits đã sort theo điểm giảm dần
        t = pts_of(h.video, h.n)
        if t is None:
            out.append(h)
            continue
        times = kept_by_video.setdefault(h.video, [])
        if any(abs(t - kt) < window_s for kt in times):
            continue
        times.append(t)
        out.append(h)
    return out


def dedup_by_video(hits: list[Hit], max_per_video: int = C.DEDUP_DEFAULT) -> list[Hit]:
    """Port NGUYÊN từ engine.py:390. LUÔN gọi với max_per_video=config.DEDUP_DEFAULT
    tường minh ở call site — KHÔNG dựa vào default của hàm (giá trị 8 đã đo, không
    phải giá trị 3 lúc chưa đo)."""
    seen: dict[str, int] = {}
    out = []
    for h in hits:
        c = seen.get(h.video, 0)
        if c < max_per_video:
            out.append(h)
            seen[h.video] = c + 1
    return out


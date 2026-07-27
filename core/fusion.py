"""Hợp nhất đa tín hiệu. Port từ `system/aic/engine.py` — xem plan mục "Điều
chỉnh kiến trúc: từ FAISS-in-RAM sang Milvus/ES" cho lý do từng hàm khác bản gốc.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core import config as C
from core.repositories.milvus_repo import MilvusRepo


@dataclass
class Hit:
    id: str
    video: str
    n: int
    frame_idx: int
    score: float


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


def maxmean_clauses(clause_vecs: np.ndarray, milvus_repo: MilvusRepo, collection: str,
                     topk: int = C.MAXMEAN_TOPK_PER_CLAUSE,
                     alpha: float = C.MAXMEAN_ALPHA) -> list[tuple[str, float]]:
    """maxmean đa mệnh đề CỦA CÙNG 1 query, trên 1 collection (thường: metaclip2).

    Hệ cũ có ma trận đầy đủ trong RAM nên tính max/mean trên TOÀN BỘ N keyframe.
    Ở đây mỗi mệnh đề chỉ có top-`topk` (Milvus search) — hợp union các id xuất hiện
    ở BẤT KỲ mệnh đề nào thành candidate pool, rồi tính max+alpha*mean CHỈ trên các
    mệnh đề mà id đó THẬT SỰ xuất hiện (không gán 0 cứng cho id vắng mặt — ngoài
    top-800/167,850 gần như chắc chắn không phải ứng viên tốt, đánh đổi chấp nhận được).

    score = max_c cos(c,kf) + alpha * mean_c cos(c,kf) — công thức port nguyên
    (engine.py:216), đã đo thắng RRF/MAX/MEAN thuần trên benchmark manual.
    """
    if clause_vecs.shape[0] == 0:
        return []
    rows = milvus_repo.search_many_scored(collection, clause_vecs, topk)
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


def superglobal_rerank(qvec: np.ndarray, cand_ids: list[str], cand_vecs: np.ndarray,
                        k_neighbor: int = C.SUPERGLOBAL_K) -> tuple[list[str], np.ndarray]:
    """Port NGUYÊN từ engine.py:32 — GIỮ TẮT (config.USE_SUPERGLOBAL=False). Đo cô
    lập dương nhưng đo qua pipeline thật thì hại (RRF đầy đủ đã cho tín hiệu sắc,
    làm mượt bằng láng giềng làm nhoè tín hiệu đã sắc) — chỉ bật lại nếu A/B lại
    qua pipeline thật cho kết quả dương."""
    if len(cand_ids) < 2:
        return cand_ids, np.zeros(len(cand_ids))
    k = min(k_neighbor, len(cand_ids))
    sims = cand_vecs @ qvec
    top_k = np.argsort(-sims)[:k]
    expanded_q = cand_vecs[top_k].max(axis=0)
    expanded_q = expanded_q / (np.linalg.norm(expanded_q) + 1e-8)

    sim_matrix = cand_vecs @ cand_vecs.T
    nn_idx = np.argsort(-sim_matrix, axis=1)[:, :k]
    refined = cand_vecs[nn_idx].mean(axis=1)
    refined = refined / (np.linalg.norm(refined, axis=1, keepdims=True) + 1e-8)

    s_final = (refined @ qvec + cand_vecs @ expanded_q) / 2
    order = np.argsort(-s_final)
    return [cand_ids[i] for i in order], s_final[order]

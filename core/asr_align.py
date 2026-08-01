"""Align kết quả ASR (đoạn, không phải keyframe) sang keyframe cụ thể. Hệ cũ có
`asr_index.py` PRE-align lúc build index; ở đây `aic_asr` trên ES chỉ lưu đoạn
(video,start,end,text) nên phải tự align ±2s ở QUERY-TIME, dùng `media_index` để
biết pts_time của từng keyframe trong video đó.

THÊM (semantic ASR): `search_asr_as_frames` ở trên khớp TỪ (Meilisearch) — câu
hỏi phải dùng ĐÚNG từ ASR nói ra mới ra kết quả. `search_asr_semantic_as_frames`
dùng embedding (Qwen3-Embedding-4B, nhánh FAISS "asr_emb" — xem
indexing/kaggle/12_asr_embed.py + indexing/build_faiss.py) để khớp Ý NGHĨA, vd
câu hỏi "giá xăng tăng" vẫn ra được đoạn ASR nói "giá nhiên liệu leo thang" dù
không chung từ nào. Cùng chung 1 bước align ±2s -> frame, chỉ khác NGUỒN đoạn
(video,start,end,score) đầu vào.
"""
from __future__ import annotations

import numpy as np

from core.media_index import MediaIndex
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo

ALIGN_WINDOW_S = 2.0


def align_segments_to_frames(segments: list[tuple[str, float, float, float]],
                              media_index: MediaIndex, window_s: float = ALIGN_WINDOW_S) -> list[str]:
    """Public (dùng lại ở api/routers/search.py cho strict_text_filter, margin
    RỘNG HƠN window_s mặc định — xem core.config.ASR_FILTER_MARGIN_S)."""
    best: dict[str, float] = {}
    for video, start, end, score in segments:
        lo, hi = start - window_s, end + window_s
        for n, pts in media_index.video_ns_pts(video):
            if lo <= pts <= hi:
                doc_id = f"{video}:{n:06d}"
                if score > best.get(doc_id, -1.0):
                    best[doc_id] = score
    return [doc_id for doc_id, _ in sorted(best.items(), key=lambda kv: -kv[1])]


def search_asr_as_frames(es_repo: MeiliRepo, media_index: MediaIndex, query_text: str,
                          size: int = 200, videos: list[str] | None = None) -> list[str]:
    """Trả rank-list id "{video}:{n:06d}" (sort theo es_score giảm dần, dedup giữ
    điểm cao nhất khi 1 keyframe rơi vào nhiều đoạn ASR khớp) — đúng dạng
    core.fusion.rrf() cần. `videos`: TÙY CHỌN — giới hạn video_scope (mục 3)."""
    segments = es_repo.search_asr(query_text, size, videos=videos)
    if not segments:
        return []
    return align_segments_to_frames(segments, media_index)


def search_asr_semantic_as_frames(faiss_repo: FaissRepo, media_index: MediaIndex,
                                   query_vec: np.ndarray, size: int = 200) -> list[str]:
    """Giống search_asr_as_frames() nhưng khớp NGỮ NGHĨA qua nhánh FAISS "asr_emb"
    thay vì khớp từ Meilisearch — `query_vec` PHẢI encode bằng capemb (Qwen3-
    Embedding-4B, cùng model đã encode nhánh này lúc build, prompt_name="query").
    Trả [] nếu chưa build nhánh asr_emb (an toàn, không lỗi)."""
    if not faiss_repo.has_branch("asr_emb"):
        return []
    hits = faiss_repo.search_scored("asr_emb", query_vec, size)
    if not hits:
        return []
    segments = []
    for doc_id, score in hits:
        extra = faiss_repo.get_meta_extra("asr_emb", doc_id, "video", "start", "end")
        if extra is None:
            continue
        video, start, end = extra
        segments.append((video, float(start), float(end), score))
    return align_segments_to_frames(segments, media_index)

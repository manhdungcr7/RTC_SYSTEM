"""Align kết quả ASR (đoạn, không phải keyframe) sang keyframe cụ thể. Hệ cũ có
`asr_index.py` PRE-align lúc build index; ở đây `aic_asr` trên ES chỉ lưu đoạn
(video,start,end,text) nên phải tự align ±2s ở QUERY-TIME, dùng `media_index` để
biết pts_time của từng keyframe trong video đó.
"""
from __future__ import annotations

from core.media_index import MediaIndex
from core.repositories.es_repo import EsRepo

ALIGN_WINDOW_S = 2.0


def search_asr_as_frames(es_repo: EsRepo, media_index: MediaIndex, query_text: str,
                          size: int = 200) -> list[str]:
    """Trả rank-list id "{video}:{n:06d}" (sort theo es_score giảm dần, dedup giữ
    điểm cao nhất khi 1 keyframe rơi vào nhiều đoạn ASR khớp) — đúng dạng
    core.fusion.rrf() cần."""
    segments = es_repo.search_asr(query_text, size)
    if not segments:
        return []

    best: dict[str, float] = {}
    for video, start, end, score in segments:
        lo, hi = start - ALIGN_WINDOW_S, end + ALIGN_WINDOW_S
        for n, pts in media_index.video_ns_pts(video):
            if lo <= pts <= hi:
                doc_id = f"{video}:{n:06d}"
                if score > best.get(doc_id, -1.0):
                    best[doc_id] = score

    return [doc_id for doc_id, _ in sorted(best.items(), key=lambda kv: -kv[1])]

"""POST /temporal — TRAKE (chuỗi sự kiện theo thứ tự trong cùng video)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_encoders, get_es, get_media_index, get_milvus
from api.schemas.search import SearchHit
from api.schemas.temporal import TemporalCandidate, TemporalRequest, TemporalResponse
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.query_service import strip_temporal_framing
from core.repositories.faiss_repo import FaissRepo
from core.repositories.meili_repo import MeiliRepo
from core.temporal import search_temporal

router = APIRouter()


@router.post("/temporal", response_model=TemporalResponse)
def temporal(req: TemporalRequest,
             milvus: FaissRepo = Depends(get_milvus),
             es: MeiliRepo = Depends(get_es),
             encoders: QueryEncoders = Depends(get_encoders),
             media_index: MediaIndex = Depends(get_media_index)) -> TemporalResponse:
    # Cắt khung mẫu "Khoảnh khắc đầu tiên/cuối cùng thấy..." TRƯỚC khi dùng cho cả
    # encode thị giác lẫn OCR/ASR — ĐO THẬT: giữ nguyên khung mẫu làm OCR khớp NHẦM
    # theo từ chung ("khoảnh khắc","cắt"...) thay vì từ phân biệt thật (xem
    # core.query_service.strip_temporal_framing).
    cleaned = [strip_temporal_framing(e) for e in req.events]
    texts = [f"{req.context} {e}".strip() if req.context else e for e in cleaned]
    event_vecs = encoders.metaclip2.encode(texts)

    # event_texts=texts (câu gốc, thường tiếng Việt) -> khớp OCR/ASR (cũng tiếng
    # Việt) — xem docstring core.temporal cho lý do thêm bước này (cận cảnh
    # tay+dao+thớt nhìn giống hệt nhau giữa các nguyên liệu khác nhau, cần chữ/lời
    # nói để phân biệt).
    results = search_temporal(event_vecs, milvus, "metaclip2", per_event=req.per_event, topk=req.topk,
                               event_texts=texts, es_repo=es, media_index=media_index)

    candidates = [
        TemporalCandidate(
            video=hits[0].video,
            total_score=total,
            hits=[SearchHit(id=h.id, video=h.video, n=h.n, frame_idx=h.frame_idx, score=h.score,
                             thumb_url=f"/media/frame/{h.video}/{h.n}",
                             pts_time=media_index.pts_time(h.video, h.n)) for h in hits],
        )
        for total, hits in results
    ]
    return TemporalResponse(candidates=candidates)

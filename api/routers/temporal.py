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

    # OCR/ASR mặc định dùng câu event đã cắt khung mẫu — NHƯNG người vận hành có
    # thể ghi đè tay RIÊNG từng sự kiện (req.ocr_queries[i]/asr_queries[i]) khi
    # biết chính xác chữ/lời cần tìm, bỏ qua đoán tự động cho đúng sự kiện đó
    # (các sự kiện không ghi đè vẫn dùng tự động — không phải tất-cả-hoặc-không-gì).
    def _override(manual: list[str] | None, i: int, fallback: str) -> str:
        if manual and i < len(manual) and manual[i].strip():
            return manual[i]
        return fallback

    ocr_texts = [_override(req.ocr_queries, i, t) for i, t in enumerate(texts)]
    asr_texts = [_override(req.asr_queries, i, t) for i, t in enumerate(texts)]

    anchor = tuple(req.anchor_indices) if req.anchor_indices and len(req.anchor_indices) == 2 else None
    results = search_temporal(event_vecs, milvus, "metaclip2", per_event=req.per_event, topk=req.topk,
                               ocr_texts=ocr_texts, asr_texts=asr_texts, es_repo=es,
                               media_index=media_index, lam=req.lambda_penalty, anchor_indices=anchor)

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

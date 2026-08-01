"""POST /similar — image-to-image thuần qua DINOv3 (không có text tower). 2 cách:
  - /similar          : "similar to 1 keyframe ĐÃ CÓ SẴN trong index" (dùng thẳng
                         vector DINOv3 đã nạp lúc indexing, KHÔNG cần encode lại)
                         — đúng nhu cầu "dùng frame này cho image-similarity" ở
                         FrameDetailModal.
  - /similar/upload   : "tìm ảnh giống" khi người dùng UPLOAD 1 ảnh NGOÀI (chưa có
                         vector sẵn) — encode qua DINOv3 remote (core.query_encoders.
                         RemoteImageEncoder, xem indexing/kaggle/11_encode_service.py)
                         rồi search y hệt. CẦN REMOTE_ENCODER_URL đang chạy (không có
                         bản in-process local, backend container không cài torch).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_encoders, get_media_index, get_milvus
from api.schemas.search import SearchHit
from api.schemas.similar import SimilarRequest, SimilarResponse
from core.media_index import MediaIndex
from core.query_encoders import QueryEncoders
from core.repositories.faiss_repo import FaissRepo

router = APIRouter()


def _hits_from_scored(scored: list[tuple[str, float]], milvus: FaissRepo,
                       media_index: MediaIndex) -> list[SearchHit]:
    meta = milvus.fetch_by_ids("dinov3", [i for i, _ in scored])
    return [SearchHit(id=i, video=meta[i][0], n=meta[i][1], frame_idx=meta[i][2], score=s,
                       thumb_url=f"/media/frame/{meta[i][0]}/{meta[i][1]}",
                       pts_time=media_index.pts_time(meta[i][0], meta[i][1]))
            for i, s in scored if i in meta]


@router.post("/similar", response_model=SimilarResponse)
def similar(req: SimilarRequest, milvus: FaissRepo = Depends(get_milvus),
            media_index: MediaIndex = Depends(get_media_index)) -> SimilarResponse:
    doc_id = f"{req.video}:{req.n:06d}"
    vec = milvus.fetch_vector_by_id("dinov3", doc_id)
    if vec is None:
        raise HTTPException(404, f"không tìm thấy vector dinov3 cho {doc_id}")

    scored = milvus.search_scored("dinov3", vec, req.topk + 1)   # +1 vì chính nó luôn hạng 1
    scored = [(i, s) for i, s in scored if i != doc_id][:req.topk]
    return SimilarResponse(hits=_hits_from_scored(scored, milvus, media_index))


@router.post("/similar/upload", response_model=SimilarResponse)
async def similar_upload(file: UploadFile = File(...), topk: int = 100,
                          milvus: FaissRepo = Depends(get_milvus),
                          encoders: QueryEncoders = Depends(get_encoders),
                          media_index: MediaIndex = Depends(get_media_index)) -> SimilarResponse:
    if encoders.dinov3_image is None:
        raise HTTPException(
            503, "Tìm theo ảnh cần REMOTE encoder (AIC_REMOTE_ENCODER_URL) đang chạy "
                 "kèm DINOv3 — xem indexing/kaggle/11_encode_service.py.")
    raw = await file.read()
    try:
        vec = encoders.dinov3_image.encode_image(raw, filename=file.filename or "image.jpg")
    except Exception as e:
        raise HTTPException(502, f"encode ảnh thất bại: {type(e).__name__}: {e}")

    scored = milvus.search_scored("dinov3", vec, topk)
    return SimilarResponse(hits=_hits_from_scored(scored, milvus, media_index))

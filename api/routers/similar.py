"""POST /similar — image-to-image thuần qua DINOv3 (không có text tower). Phạm
vi P4: chỉ hỗ trợ "similar to 1 keyframe đã có sẵn" (dùng thẳng vector DINOv3 đã
nạp lúc indexing, KHÔNG cần encode lại) — đúng nhu cầu chính của UI ("dùng frame
này cho image-similarity" ở FrameDetailModal). Upload ảnh ngoài (chưa có vector
sẵn) cần thêm 1 DINOv3 image-encoder in-process — để P7 nếu cần, không chặn core.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_media_index, get_milvus
from api.schemas.search import SearchHit
from api.schemas.similar import SimilarRequest, SimilarResponse
from core.media_index import MediaIndex
from core.repositories.faiss_repo import FaissRepo

router = APIRouter()


@router.post("/similar", response_model=SimilarResponse)
def similar(req: SimilarRequest, milvus: FaissRepo = Depends(get_milvus),
            media_index: MediaIndex = Depends(get_media_index)) -> SimilarResponse:
    doc_id = f"{req.video}:{req.n:06d}"
    vec = milvus.fetch_vector_by_id("dinov3", doc_id)
    if vec is None:
        raise HTTPException(404, f"không tìm thấy vector dinov3 cho {doc_id}")

    scored = milvus.search_scored("dinov3", vec, req.topk + 1)   # +1 vì chính nó luôn hạng 1
    scored = [(i, s) for i, s in scored if i != doc_id][:req.topk]
    meta = milvus.fetch_by_ids("dinov3", [i for i, _ in scored])

    hits = [SearchHit(id=i, video=meta[i][0], n=meta[i][1], frame_idx=meta[i][2], score=s,
                       thumb_url=f"/media/frame/{meta[i][0]}/{meta[i][1]}",
                       pts_time=media_index.pts_time(meta[i][0], meta[i][1]))
            for i, s in scored if i in meta]
    return SimilarResponse(hits=hits)

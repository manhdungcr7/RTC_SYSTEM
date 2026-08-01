"""POST /search/videos — LỌC VIDEO TRƯỚC (mục 3): tìm/duyệt video theo nội dung
(ASR+caption gộp, chỉ mục `aic_videos`) và/hoặc thể loại (suy từ kênh YouTube,
xem core.config.VIDEO_CATEGORY_MAP). ĐỘC LẬP với /search khung hình — trả kết
quả NGAY (danh sách video), người dùng TỰ QUYẾT có dùng làm `video_scope` cho
/search hay không (không ép phải làm tiếp bước lọc khung hình)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_es, get_media_index
from api.schemas.videos import VideoHit, VideoSearchRequest, VideoSearchResponse
from core import config as C
from core.media_index import MediaIndex
from core.repositories.meili_repo import MeiliRepo

router = APIRouter()


@router.post("/search/videos", response_model=VideoSearchResponse)
def search_videos(req: VideoSearchRequest, es: MeiliRepo = Depends(get_es),
                   media_index: MediaIndex = Depends(get_media_index)) -> VideoSearchResponse:
    results = es.search_videos(req.query, req.topk, category=req.category)

    hits = []
    for video, score in results:
        ns_pts = media_index.video_ns_pts(video)
        first_n = ns_pts[0][0] if ns_pts else 1
        doc = es.videos.get_document(video)
        hits.append(VideoHit(
            video=video, score=score,
            category=getattr(doc, "category", "Khác"),
            title=getattr(doc, "title", ""),
            thumb_url=f"/media/frame/{video}/{first_n}",
        ))

    return VideoSearchResponse(hits=hits, categories=C.VIDEO_CATEGORIES)

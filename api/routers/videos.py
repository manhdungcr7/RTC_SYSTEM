"""Dữ liệu cấp VIDEO.

1) POST /search/videos — thu hẹp phạm vi TRƯỚC khi tìm khung hình: tìm/duyệt
   video theo thể loại và/hoặc nội dung (lời thoại / mô tả cảnh / cả hai). ĐỘC
   LẬP với /search: trả kết quả ngay, người dùng TỰ QUYẾT có dùng làm phạm vi
   hay không — không ép phải làm tiếp bước sau.

2) GET /videos/{video}/map|transcript|ocr|keyframes — dữ liệu đầy đủ của MỘT
   video. Đây là hạ tầng cho 2 đòn bẩy thủ công quan trọng nhất (nguyên tắc
   "luôn còn một đường thủ công"):
     - Đồng hồ frame_idx thời gian thực khi tua video (cần `map` + `fps`).
     - Video Workbench: đọc trọn transcript + toàn bộ chữ trên hình + duyệt hết
       keyframe bằng mắt, khi mọi tín hiệu tự động đều thất bại.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_meili, get_media_index
from api.schemas.videos import (KeyframeRow, KeyframesResponse, OcrResponse, OcrRow,
                                 TranscriptResponse, TranscriptSegment, VideoHit,
                                 VideoMapResponse, VideoMapRow, VideoSearchRequest,
                                 VideoSearchResponse)
from core import config as C
from core.media_index import MediaIndex
from core.repositories.meili_repo import MeiliRepo

router = APIRouter()


@router.post("/search/videos", response_model=VideoSearchResponse)
def search_videos(req: VideoSearchRequest, meili: MeiliRepo = Depends(get_meili),
                   media_index: MediaIndex = Depends(get_media_index)) -> VideoSearchResponse:
    results = meili.search_videos(req.query, req.topk, category=req.category, field=req.field)

    hits = []
    for video, score in results:
        ns_pts = media_index.video_ns_pts(video)
        first_n = ns_pts[0][0] if ns_pts else 1
        try:
            doc = meili.videos.get_document(video)
            category = getattr(doc, "category", "Khác")
            title = getattr(doc, "title", "")
        except Exception:
            category, title = "Khác", ""
        hits.append(VideoHit(video=video, score=score, category=category, title=title,
                              thumb_url=f"/media/thumb/{video}/{first_n}"))

    return VideoSearchResponse(hits=hits, categories=C.VIDEO_CATEGORIES)


@router.get("/videos/{video}/map", response_model=VideoMapResponse)
def video_map(video: str, media_index: MediaIndex = Depends(get_media_index)) -> VideoMapResponse:
    """Bảng quy đổi (n, frame_idx, pts_time) + fps của video.

    Trả NGUYÊN bảng cho client tự nội suy thay vì hỏi máy chủ mỗi lần tua — tua
    video sinh hàng chục sự kiện/giây, gọi mạng mỗi lần là không dùng được. Bảng
    chỉ vài trăm dòng/video nên rất nhẹ."""
    rows = media_index.full_map(video)
    if not rows:
        raise HTTPException(404, f"không có bảng map cho video {video}")
    return VideoMapResponse(
        video=video, fps=media_index.fps(video),
        duration=rows[-1]["pts_time"] if rows else None,
        rows=[VideoMapRow(n=r["n"], frame_idx=r["frame_idx"], pts_time=r["pts_time"])
              for r in rows],
    )


@router.get("/videos/{video}/keyframes", response_model=KeyframesResponse)
def video_keyframes(video: str,
                     media_index: MediaIndex = Depends(get_media_index)) -> KeyframesResponse:
    """Toàn bộ keyframe của 1 video — "bức tường keyframe" trong Workbench."""
    rows = media_index.full_map(video)
    if not rows:
        raise HTTPException(404, f"không có keyframe cho video {video}")
    return KeyframesResponse(video=video, frames=[
        KeyframeRow(n=r["n"], frame_idx=r["frame_idx"], pts_time=r["pts_time"]) for r in rows])


@router.get("/videos/{video}/transcript", response_model=TranscriptResponse)
def video_transcript(video: str, meili: MeiliRepo = Depends(get_meili)) -> TranscriptResponse:
    """Trọn lời thoại của video, theo thứ tự thời gian — bấm 1 dòng là nhảy tới
    đúng giây đó trong trình phát."""
    segs = meili.all_asr_for_video(video)
    return TranscriptResponse(video=video, segments=[
        TranscriptSegment(t=s["t"], end=s["end"], text=s["text"]) for s in segs])


@router.get("/videos/{video}/ocr", response_model=OcrResponse)
def video_ocr(video: str, meili: MeiliRepo = Depends(get_meili)) -> OcrResponse:
    """Toàn bộ chữ trên hình của video theo thứ tự khung hình."""
    rows = meili.all_ocr_for_video(video)
    return OcrResponse(video=video, rows=[OcrRow(n=r["n"], text=r["text"]) for r in rows])

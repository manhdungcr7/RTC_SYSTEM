"""GET /media/* — phục vụ ảnh keyframe/video/filmstrip trực tiếp từ đĩa (đã có
sẵn local, không cần tải lại — xem core/media_index.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.deps import get_media_index
from core.media_index import MediaIndex

router = APIRouter(prefix="/media")


@router.get("/frame/{video}/{n}")
def frame(video: str, n: int, media_index: MediaIndex = Depends(get_media_index)):
    p = media_index.resolve_frame_path(video, n)
    if p is None:
        raise HTTPException(404, f"không tìm thấy keyframe {video}:{n:06d}")
    return FileResponse(p, media_type="image/webp")


@router.get("/video/{video}")
def video(video: str, media_index: MediaIndex = Depends(get_media_index)):
    p = media_index.resolve_video_path(video)
    if p is None:
        raise HTTPException(404, f"không tìm thấy video {video}")
    # FileResponse (Starlette) tự xử lý header Range -> tua video mượt trên UI.
    return FileResponse(p, media_type="video/mp4")


@router.get("/filmstrip/{video}")
def filmstrip(video: str, around: int, window: int = 10,
              media_index: MediaIndex = Depends(get_media_index)):
    ns = media_index.nearby_ns(video, around, window)
    return {"video": video, "frames": [{"n": n, "thumb_url": f"/media/frame/{video}/{n}"} for n in ns]}

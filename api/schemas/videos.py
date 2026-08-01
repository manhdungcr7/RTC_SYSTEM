"""Lọc video trước (mục 3) — xem api/routers/videos.py, core/repositories/meili_repo.py::search_videos."""
from pydantic import BaseModel


class VideoSearchRequest(BaseModel):
    query: str = ""            # rỗng + có category -> browse toàn bộ video thuộc category đó
    category: str | None = None   # xem core.config.VIDEO_CATEGORIES — None = mọi thể loại
    topk: int = 100


class VideoHit(BaseModel):
    video: str
    score: float
    category: str
    title: str
    thumb_url: str   # keyframe đầu tiên của video, đại diện


class VideoSearchResponse(BaseModel):
    hits: list[VideoHit]
    categories: list[str]   # toàn bộ thể loại có sẵn (core.config.VIDEO_CATEGORIES) — cho UI vẽ dropdown

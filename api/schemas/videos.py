"""Lọc video trước + dữ liệu cấp VIDEO (map khung hình, transcript, OCR) —
xem api/routers/videos.py."""
from typing import Literal

from pydantic import BaseModel


class VideoSearchRequest(BaseModel):
    query: str = ""            # rỗng + có category -> duyệt toàn bộ video thuộc category
    category: str | None = None
    topk: int = 100
    # Nguồn nội dung để khớp — xem MeiliRepo.search_videos. "all" rộng nhất
    # (mặc định); chọn 1 nguồn là chủ động thu hẹp khi biết manh mối nằm ở đâu.
    field: Literal["all", "asr", "caption"] = "all"


class VideoHit(BaseModel):
    video: str
    score: float
    category: str
    title: str
    thumb_url: str


class VideoSearchResponse(BaseModel):
    hits: list[VideoHit]
    categories: list[str]


# ---- Dữ liệu cấp video (cho đồng hồ frame_idx + Video Workbench) ----

class VideoMapRow(BaseModel):
    n: int
    frame_idx: int
    pts_time: float


class VideoMapResponse(BaseModel):
    """NGUỒN CHÂN LÝ cho việc quy đổi giây <-> frame_idx ở phía trình duyệt.
    Trả nguyên bảng map để client tự nội suy (tránh gọi mạng mỗi lần tua)."""
    video: str
    fps: float
    duration: float | None = None
    rows: list[VideoMapRow]


class TranscriptSegment(BaseModel):
    t: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    video: str
    segments: list[TranscriptSegment]


class OcrRow(BaseModel):
    n: int
    text: str


class OcrResponse(BaseModel):
    video: str
    rows: list[OcrRow]


class KeyframeRow(BaseModel):
    n: int
    frame_idx: int
    pts_time: float


class KeyframesResponse(BaseModel):
    video: str
    frames: list[KeyframeRow]

"""GET /media/* — phục vụ ảnh keyframe/video/filmstrip trực tiếp từ đĩa (đã có
sẵn local, không cần tải lại — xem core/media_index.py)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.deps import get_media_index, get_meili
from api.schemas.search import FrameContent, SearchHit
from core.media_index import MediaIndex
from core.repositories.meili_repo import MeiliRepo

router = APIRouter(prefix="/media")


_THUMB_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}  # keyframe không đổi


@router.get("/frame/{video}/{n}")
def frame(video: str, n: int, media_index: MediaIndex = Depends(get_media_index)):
    p = media_index.resolve_frame_path(video, n)
    if p is None:
        raise HTTPException(404, f"không tìm thấy keyframe {video}:{n:06d}")
    return FileResponse(p, media_type="image/webp", headers=_THUMB_HEADERS)


@router.get("/thumb/{video}/{n}")
def thumb(video: str, n: int, media_index: MediaIndex = Depends(get_media_index)):
    """Bản 320px — lưới kết quả dùng cái này thay vì /frame (ảnh gốc) để tải
    nhanh (xem indexing/build_thumbnails.py). Tự rơi về ảnh gốc nếu chưa
    tiền sinh, không lỗi."""
    p = media_index.resolve_thumb_path(video, n)
    if p is None:
        raise HTTPException(404, f"không tìm thấy keyframe {video}:{n:06d}")
    return FileResponse(p, media_type="image/webp", headers=_THUMB_HEADERS)


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
    return {"video": video, "frames": [{"n": n, "thumb_url": f"/media/thumb/{video}/{n}"} for n in ns]}


@router.get("/lookup/{video}", response_model=SearchHit)
def lookup(video: str, frame_idx: int = 1,
           media_index: MediaIndex = Depends(get_media_index),
           meili: MeiliRepo = Depends(get_meili)) -> SearchHit:
    """Tra tay 1 khung hình theo (video, frame_idx) — đòn bẩy thủ công "luôn còn
    đường tay" (P5): biết chắc video + số frame (vd đọc được từ đề thi hoặc tự
    tua ra) thì mở thẳng ra xem, không phải tìm bằng mô tả trước. Trả ĐÚNG
    dạng SearchHit để dùng chung modal "Giải thích" với kết quả tìm kiếm bình
    thường — kể cả xem được video tại đúng giây đó.

    `frame_idx` là số 1-based đã tính theo quy ước BTC (xem core/media_index.py)
    — mặc định 1 (khung đầu tiên) nếu không truyền, để chỉ cần gõ tên video là
    tra được ngay, không bắt buộc phải biết số frame.

    Keyframe thưa (không phải mọi frame_idx đều được lập chỉ mục) nên tra ra
    KEYFRAME GẦN NHẤT với số đã nhập — không phải lúc nào cũng khớp tuyệt đối,
    nhưng đây là khung DUY NHẤT có đủ caption/OCR/vật thể đã trích sẵn."""
    rows = media_index.full_map(video)
    if not rows:
        raise HTTPException(404, f"không tìm thấy video {video}")
    nearest = min(rows, key=lambda r: abs(r["frame_idx"] - frame_idx))

    doc_id = f"{video}:{nearest['n']:06d}"
    doc = meili.get_frame_docs([doc_id]).get(doc_id, {})
    pts = nearest["pts_time"]
    asr_window = meili.asr_segments_for_video(video, pts - 5, pts + 8, size=5)
    content = FrameContent(caption=doc.get("caption"), ocr=doc.get("ocr"),
                            objects=doc.get("objects"), asr_window=asr_window)

    return SearchHit(id=doc_id, video=video, n=nearest["n"], frame_idx=nearest["frame_idx"],
                      score=0.0, thumb_url=f"/media/thumb/{video}/{nearest['n']}",
                      pts_time=pts, rank=0, content=content)


@router.get("/frame_at/{video}")
def frame_at(video: str, t: float, media_index: MediaIndex = Depends(get_media_index)):
    """Trích khung hình tại GIÂY BẤT KỲ bằng ffmpeg (không giới hạn ở keyframe
    thưa đã lập chỉ mục).

    Đây là đường thoát cho tình huống khoảnh khắc cần tìm rơi vào GIỮA hai
    keyframe — với keyframe thưa, cảnh diễn ra nhanh có thể không được bắt trọn
    bởi bất kỳ keyframe nào. Dùng cho filmstrip bước 1s/5s và xem xác nhận khi
    người dùng tự tua tay.

    Cache mạnh: cùng (video, giây) luôn ra cùng một ảnh."""
    import os
    import subprocess
    import tempfile
    import uuid

    p = media_index.resolve_video_path(video)
    if p is None:
        raise HTTPException(404, f"không tìm thấy video {video}")
    if t < 0:
        raise HTTPException(400, "tham số t phải >= 0")

    out = Path(tempfile.gettempdir()) / f"aic_frameat_{video}_{t:.3f}.jpg"
    if not out.exists():
        # ĐÃ SỬA — RỦI RO ĐỒNG THỜI THẬT: nhiều người dùng cùng lúc (5-10 người)
        # có thể tua tới CÙNG giây của CÙNG video cùng lúc -> 2 request trước đây
        # cùng ghi thẳng vào `out`, có thể chồng nhau giữa chừng và người đọc
        # (FileResponse) nhận file JPEG hỏng/dở dang. Giờ mỗi tiến trình ffmpeg
        # ghi ra 1 file TẠM RIÊNG (tên có PID+random), xong mới os.replace() ĐỔI
        # TÊN NGUYÊN TỬ sang đường dẫn cuối — mọi request đọc `out` luôn thấy
        # HOẶC file cũ trọn vẹn, HOẶC file mới trọn vẹn, không bao giờ dở dang.
        tmp = out.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
        # -ss TRƯỚC -i: seek nhanh (không giải mã từ đầu). -frames:v 1: đúng 1 ảnh.
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{t:.3f}",
               "-i", str(p), "-frames:v", "1", "-q:v", "3", "-y", str(tmp)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30)
        except FileNotFoundError:
            raise HTTPException(
                503, "ffmpeg chưa có trong image backend — dựng lại image để dùng tính năng này")
        except subprocess.TimeoutExpired:
            tmp.unlink(missing_ok=True)
            raise HTTPException(504, "trích khung hình quá lâu, thử lại")
        if r.returncode != 0 or not tmp.exists():
            tmp.unlink(missing_ok=True)
            raise HTTPException(500, f"ffmpeg lỗi: {r.stderr.decode('utf-8', 'ignore')[:300]}")
        os.replace(tmp, out)   # nguyên tử trên cùng ổ đĩa — không có trạng thái dở dang
    return FileResponse(out, media_type="image/jpeg", headers=_THUMB_HEADERS)

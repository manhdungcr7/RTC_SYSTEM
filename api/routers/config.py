"""GET/PUT /config/encoder — đọc và ĐỔI NÓNG địa chỉ encoder Kaggle CHO PHIÊN
ĐANG CHẠY (không ghi xuống đĩa, không sống sót qua lần khởi động lại).

VÌ SAO CẦN: phiên Kaggle miễn phí có giới hạn giờ chạy, mỗi lần khởi động lại là
URL ngrok + API key đổi. Đổi qua đây áp dụng NGAY, không cần dựng lại container.

VÌ SAO KHÔNG LƯU BỀN (đã bỏ — xem lịch sử): từng ghi ra file rồi tự nạp lại lúc
startup, nhưng ĐÃ GẶP LỖI THẬT — file cũ (key hết hạn) thắng .env mới mỗi lần
container khởi động lại, gây 401 Unauthorized âm thầm. Nguồn chân lý DUY NHẤT
cho lần khởi động là `.env` (`AIC_REMOTE_ENCODER_URL/KEY`) — sửa ở đó rồi restart
là cách đúng và luôn đáng tin, đúng thói quen thao tác thật của người vận hành."""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

from config import settings
from core.query_encoders import QueryEncoders

router = APIRouter(prefix="/config")

# Chỉ giữ lại đường dẫn để main.py dọn file cũ (từ bản trước khi sửa lỗi) —
# không còn ghi mới vào đây nữa.
OVERRIDE_PATH = settings.ARTIFACTS_ROOT / "encoder_override.json"


class EncoderConfig(BaseModel):
    url: str
    key: str = ""


def apply_override(data: dict):
    """Đặt vào settings + biến môi trường để mọi nơi đọc lại đều thấy giá trị mới."""
    url = (data.get("url") or "").strip().rstrip("/")
    key = (data.get("key") or "").strip()
    settings.REMOTE_ENCODER_URL = url or None
    settings.REMOTE_ENCODER_KEY = key
    os.environ["AIC_REMOTE_ENCODER_URL"] = url
    os.environ["AIC_REMOTE_ENCODER_KEY"] = key


@router.get("/encoder")
def get_encoder():
    """KHÔNG trả API key ra ngoài — chỉ báo đã có key hay chưa."""
    return {"url": settings.REMOTE_ENCODER_URL, "has_key": bool(settings.REMOTE_ENCODER_KEY)}


@router.post("/encoder")
def set_encoder(cfg: EncoderConfig, request: Request):
    data = {"url": cfg.url.strip().rstrip("/"), "key": cfg.key.strip()}
    apply_override(data)   # đổi NÓNG cho phiên hiện tại — KHÔNG ghi xuống đĩa
                            # (xem docstring module: đây là lý do gây lỗi 401 trước đây)

    # Nạp lại encoder — RemoteBranchEncoder chỉ giữ url/key nên rất rẻ (không tải
    # model). Cache vector cũ VẪN DÙNG ĐƯỢC vì khoá theo (nhánh, câu chữ), không
    # theo địa chỉ máy chủ.
    old = getattr(request.app.state, "encoders", None)
    try:
        request.app.state.encoders = QueryEncoders().load_all()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if old is not None:
        try:
            old.shutdown()
        except Exception:
            pass

    # Thử gọi thật để báo lại ngay là sống hay chết, thay vì bắt người dùng đoán.
    import requests as rq
    try:
        r = rq.get(f"{data['url']}/health", headers={"X-API-Key": data["key"]}, timeout=8)
        r.raise_for_status()
        return {"ok": True, "detail": r.json()}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

from pydantic import BaseModel

from api.schemas.search import SearchHit


class TemporalRequest(BaseModel):
    events: list[str]
    context: str = ""
    topk: int = 100
    per_event: int = 1500
    # Ghi đè tay OCR/ASR RIÊNG cho từng sự kiện (song song với `events`, cùng độ
    # dài, phần tử rỗng = dùng tự động theo câu event) — hệ "truyền thống có
    # tương tác": người biết chính xác chữ/lời của TỪNG khoảnh khắc thì tự nhập,
    # không phải đoán tự động cho cả 4 sự kiện giống nhau.
    ocr_queries: list[str] | None = None
    asr_queries: list[str] | None = None
    # None = dùng TRAKE_LAMBDA mặc định (phạt khoảng cách). Đặt 0 khi các sự kiện
    # KHÔNG cần gần nhau về thời gian (vd "vượt lên" rồi rất lâu sau "về đích").
    lambda_penalty: float | None = None
    # Chỉ số 2 sự kiện dùng làm NEO thị giác cho boundary-anchor (thay vì mặc
    # định E1/En) — vd query múa lân 4 sự kiện, cặp giữa (E2,E3) đặc trưng/dễ
    # nhận diện thị giác hơn E1/E4. None = (0, len(events)-1) như cũ.
    anchor_indices: list[int] | None = None


class TemporalCandidate(BaseModel):
    video: str
    total_score: float
    hits: list[SearchHit]   # 1 hit / sự kiện, đúng thứ tự E1..En


class TemporalResponse(BaseModel):
    candidates: list[TemporalCandidate]

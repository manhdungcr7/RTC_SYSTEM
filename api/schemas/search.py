from typing import Literal

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    kind: Literal["kis", "qa", "trake"] = "kis"
    topk: int = 100
    use_expansion: bool = True   # LLM query-expansion cho nhánh metaclip2 (nếu có key)

    # Ghi đè TAY — người vận hành biết chính xác cần tìm chữ/lời gì thì tự nhập,
    # bỏ qua bước tự động (LLM trích từ khoá / regex cue) vốn có thể đoán sai hoặc
    # bị pha loãng bởi câu dài (xem core.query_service.extract_ocr_keywords). Để
    # trống (None) -> hành vi tự động như cũ, không đổi gì.
    ocr_query: str | None = None
    asr_query: str | None = None
    object_query: str | None = None   # có giá trị -> LUÔN bật nhánh object+màu (bỏ qua regex gate)


class SearchHit(BaseModel):
    id: str
    video: str
    n: int
    frame_idx: int
    score: float
    thumb_url: str
    pts_time: float | None = None   # giây trong video gốc — None nếu maps CSV thiếu (hiếm)


class SignalInfo(BaseModel):
    """1 dòng minh bạch hoá: nguồn tín hiệu nào đã THẬT SỰ tham gia RRF, trọng số
    bao nhiêu, và câu/từ khoá cụ thể đã dùng — để người vận hành hiểu vì sao ra
    kết quả đó và biết chỗ nào cần tự ghi đè tay."""
    name: str
    weight: float
    query_text: str | None = None
    n_hits: int = 0


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    clauses_metaclip2: list[str]
    clauses_en: list[str]
    ocr_keywords: list[str] = []
    signals_used: list[SignalInfo] = []

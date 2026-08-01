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

    # Chọn tay nhánh MODEL EMBEDDING nào tham gia (metaclip2/beit3/pecore/capemb/
    # asr_emb/dinov3) — None = hành vi mặc định cũ (bật theo ENABLED_BRANCHES +
    # trọng số > 0, xem api/routers/search.py). UI mặc định chỉ tích metaclip2
    # (nhánh CHÍNH, bắt buộc) — các nhánh khác NẶNG hơn (gọi thêm model từ xa) nên
    # để người dùng tự bật khi cần, không ép chạy hết mỗi lần tìm.
    models: list[str] | None = None

    # TRỌNG SỐ ĐỘNG — người dùng tự ghi đè trọng số fusion CHO REQUEST NÀY (không
    # đổi giá trị mặc định trong core/config.py, chỉ override tại chỗ). Key = tên
    # tín hiệu ("metaclip2","pecore","beit3","capemb","dinov3","asr_emb",
    # "ocr","ocr_keyword","asr","object","entity"). Thiếu key nào -> dùng mặc định
    # đã đo (theo `kind`) như cũ. None/rỗng = hành vi cũ hoàn toàn.
    weights: dict[str, float] | None = None

    # TÍCH HỢP DINOv3 (mục "tìm theo ảnh" giờ tham gia CHUNG vào /search thay vì
    # tách riêng /similar) — cho query 1 ẢNH THAM CHIẾU, CHỌN 1 TRONG 2 NGUỒN:
    #   - ref_video/ref_n: 1 keyframe ĐÃ CÓ SẴN trong index (lấy lại vector, không
    #     cần encode lại — xem FaissRepo.fetch_vector_by_id).
    #   - ref_image_b64: ảnh UPLOAD ngoài (data URI hoặc base64 thuần), encode qua
    #     REMOTE DINOv3 (core.query_encoders.RemoteImageEncoder). CẦN REMOTE
    #     encoder đang chạy — không có sẽ bỏ qua êm tín hiệu này (không lỗi).
    # Có 1 trong 2 -> thêm tín hiệu "dinov3" vào RRF chung, trọng số theo
    # DINOV3_WEIGHT (hoặc weights["dinov3"] nếu ghi đè).
    ref_video: str | None = None
    ref_n: int | None = None
    ref_image_b64: str | None = None

    # LỌC VIDEO TRƯỚC (mục 3) — danh sách video giới hạn phạm vi tìm (lấy từ
    # POST /search/videos, xem api/routers/videos.py). None/rỗng = tìm toàn kho
    # như cũ. Áp dụng CHO MỌI nhánh (thị giác qua FaissRepo.search_within_ids,
    # OCR/ASR/object qua Meilisearch filter video IN [...]).
    video_scope: list[str] | None = None

    # STRICT OCR/ASR FILTER (mục 4) — khi True VÀ có khớp OCR/ASR độ tin cậy cao
    # (>= core.config.OCR_FILTER_CONFIDENCE/ASR_FILTER_CONFIDENCE), giới hạn HẲN
    # các nhánh thị giác chỉ search trong tập khung hình đã khớp (± sai số, xem
    # OCR_FILTER_MARGIN_FRAMES/ASR_FILTER_MARGIN_S) thay vì chỉ CỘNG trọng số vào
    # RRF như bình thường. Không khớp đủ tin cậy -> tự động rơi về fusion mềm như
    # cũ (không lỗi, không rỗng kết quả). Mặc định False (giữ hành vi cũ).
    strict_text_filter: bool = False


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
    # Mục 4 — minh bạch hoá: có thật sự kích hoạt strict filter không (có thể
    # False dù req.strict_text_filter=True, nếu không tìm được khớp đủ tin cậy),
    # và tập ứng viên còn lại sau khi lọc rộng bao nhiêu id.
    strict_filter_applied: bool = False
    strict_filter_pool_size: int | None = None

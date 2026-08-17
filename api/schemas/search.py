"""Hợp đồng POST /search.

NGUYÊN TẮC TƯƠNG THÍCH: các trường "phẳng" cũ (ocr_query, asr_query, weights,
video_scope...) VẪN hoạt động y như trước — frontend cũ không gãy. Các trường
CÓ CẤU TRÚC mới (ocr, asr, signals, clauses, negative, feedback...) là đường
dành cho giao diện mới; khi có mặt thì chúng THẮNG trường phẳng tương ứng.
Xem api/routers/search.py::_resolve_* để biết thứ tự ưu tiên chính xác.
"""
from typing import Literal

from pydantic import BaseModel


# ==================== CÁC KHỐI CÓ CẤU TRÚC (giao diện mới) ====================

class SignalConfig(BaseModel):
    """1 kênh trên "bàn trộn tín hiệu". `enabled=False` BỎ HẲN nhánh khỏi tính
    toán (nhanh hơn); weight=0 vẫn chạy nhưng không góp điểm (để so sánh)."""
    enabled: bool = True
    weight: float | None = None      # None = dùng mặc định theo `kind`


class ClauseConfig(BaseModel):
    """Mệnh đề thị giác do NGƯỜI DÙNG xác nhận/sửa (P4: LLM chỉ đề xuất)."""
    text: str
    weight: float = 1.0
    enabled: bool = True


class ClauseFusion(BaseModel):
    mode: Literal["max_alpha_mean"] = "max_alpha_mean"
    alpha: float = 0.3


class OcrConfig(BaseModel):
    """`mode="filter"` = LỌC CỨNG (các nhánh khác chỉ tìm trong tập đã khớp);
    `mode="score"` = chỉ cộng điểm vào RRF.

    CHỈ 1 CƠ CHẾ KHỚP DUY NHẤT (đã bỏ lựa chọn contains/phrase/prefix + thanh
    "dung sai lỗi chính tả" trước đây — ĐÃ ĐO: người dùng không phân biệt được ý
    nghĩa các lựa chọn đó, và thanh dung sai KHÔNG THẬT SỰ chỉnh được gì — dung
    sai lỗi chính tả của Meilisearch là cài đặt CẤP INDEX, không chỉnh được theo
    từng truy vấn). Cơ chế cố định: yêu cầu khớp ĐỦ mọi từ đã gõ (thứ tự tự do),
    mỗi từ vẫn hưởng dung sai lỗi chính tả mặc định của index — đúng nhu cầu
    thật: người dùng chỉ gõ vài từ NHỚ ĐƯỢC, không cần biết hết chữ trong ảnh."""
    query: str = ""
    mode: Literal["score", "filter"] = "score"


class AsrConfig(BaseModel):
    """`window_before/after` BẤT ĐỐI XỨNG có chủ đích — lời dẫn thường đi TRƯỚC
    hình minh hoạ trong tin tức, nên cửa sổ "sau" cần rộng hơn."""
    query: str = ""
    lexical: bool = True             # khớp TỪ (Meilisearch)
    semantic: bool = True            # khớp Ý NGHĨA (nhánh FAISS asr_emb)
    mode: Literal["score", "filter"] = "score"
    window_before: float = 3.0
    window_after: float = 5.0


class ObjectCond(BaseModel):
    """1 điều kiện vật thể — token đã index dạng "cls color" (YOLO26x).

    ĐÃ BỎ "vị trí trên lưới 3x3" (từng có, xem lịch sử) — ĐO THỰC TẾ: ít tác
    dụng phân biệt (YOLO26x không định vị đủ chính xác để người dùng tin cậy
    chọn đúng ô) mà làm giao diện rườm rà thêm 1 bước không cần thiết."""
    cls: str
    color: str | None = None
    min_count: int = 1


class NegativeConfig(BaseModel):
    """Mệnh đề LOẠI TRỪ — đẩy nhóm kết quả sai xuống. Đòn bẩy mạnh cho câu mơ hồ
    (mô tả thêm cái mình muốn thường kém hiệu quả hơn đẩy cái mình KHÔNG muốn)."""
    text: str = ""
    weight: float = 0.45
    hard_threshold: float | None = None   # có -> LOẠI HẲN khung vượt ngưỡng tương đồng


class FrameRef(BaseModel):
    video: str
    n: int


class FeedbackConfig(BaseModel):
    """Phản hồi liên quan (Rocchio) — chạy hoàn toàn trong RAM trên FAISS, KHÔNG
    cần gọi GPU: q' = q + beta*mean(vector ✓) - gamma*mean(vector ✗)."""
    positive: list[FrameRef] = []
    negative: list[FrameRef] = []
    beta: float = 0.6
    gamma: float = 0.3


class VideoScopeConfig(BaseModel):
    video_ids: list[str] = []
    invert: bool = False             # True = LOẠI TRỪ các video này


class FusionConfig(BaseModel):
    method: Literal["rrf", "weighted_sum"] = "rrf"
    k: int = 60


# ==================== REQUEST ====================

class SearchRequest(BaseModel):
    query: str = ""
    kind: Literal["kis", "qa", "trake"] = "kis"
    topk: int = 100
    use_expansion: bool = True   # LLM tách mệnh đề (chỉ ĐỀ XUẤT, người dùng sửa được)

    # Bật/tắt HẲN việc tự động tách mệnh đề (LLM hoặc heuristic) — người dùng có
    # thể không muốn máy tự quyết định tách câu, chỉ muốn dùng NGUYÊN câu gốc.
    # False -> encode nguyên câu query làm 1 mệnh đề DUY NHẤT, KHÔNG gọi LLM/tách
    # câu (kể cả clauses_metaclip2 lẫn clauses_en cho pecore/beit3) — nhưng vẫn
    # LUÔN dịch sang tiếng Anh cho pecore/beit3 (2 nhánh này chỉ hiểu tiếng Anh,
    # không liên quan gì tới việc có tách câu hay không). `clauses` (ghi đè tay,
    # nếu có) LUÔN thắng cờ này — đây là quyết định NGƯỜI DÙNG đã chủ động làm.
    split_clauses: bool = True

    # ---- Đường CŨ (phẳng) — giữ nguyên để frontend cũ không gãy ----
    ocr_query: str | None = None
    asr_query: str | None = None
    object_query: str | None = None
    models: list[str] | None = None
    weights: dict[str, float] | None = None
    ref_video: str | None = None
    ref_n: int | None = None
    ref_image_b64: str | None = None
    video_scope: list[str] | None = None
    strict_text_filter: bool = False

    # ---- Đường MỚI (có cấu trúc) — thắng đường cũ khi có mặt ----
    signals: dict[str, SignalConfig] | None = None
    clauses: list[ClauseConfig] | None = None        # None = để LLM tách như cũ
    clause_fusion: ClauseFusion | None = None
    translations: dict[int, str] | None = None       # ghi đè bản dịch theo chỉ số mệnh đề
    ocr: OcrConfig | None = None
    asr: AsrConfig | None = None
    objects: list[ObjectCond] | None = None
    negative: NegativeConfig | None = None
    feedback: FeedbackConfig | None = None
    scope: VideoScopeConfig | None = None
    fusion: FusionConfig | None = None
    per_video_cap: int | None = None                 # None = C.DEDUP_DEFAULT
    dedup_seconds: float | None = None               # gộp khung quá gần nhau về thời gian

    # ---- Minh bạch hoá (P1-P3) ----
    explain: bool = False            # trả kèm phân rã điểm từng nhánh/mệnh đề
    branch_lists: bool = False       # trả kèm bảng xếp hạng RIÊNG từng nhánh (tab nhánh)


# ==================== RESPONSE ====================

class BranchContribution(BaseModel):
    branch: str
    rank: int                  # thứ hạng trong nhánh đó (1-based); -1 = không có mặt
    raw: float                 # điểm thô của nhánh (cosine / _rankingScore)
    weight: float
    rrf: float                 # phần đóng góp THẬT vào điểm gộp cuối


class ClauseScore(BaseModel):
    text: str
    score: float


class FrameContent(BaseModel):
    """Nội dung đã trích sẵn của khung hình — để người dùng đối chiếu ngay mà
    không phải mở video (đặc biệt quan trọng cho Q&A đọc chữ nhỏ)."""
    caption: str | None = None
    ocr: str | None = None
    objects: str | None = None       # "person 3a red car 5c blue" — xem meili_repo
    asr_window: list[dict] = []      # [{"t": 38.1, "text": "..."}]


class HitExplain(BaseModel):
    branches: list[BranchContribution] = []
    clauses: list[ClauseScore] = []
    penalties: dict[str, float] = {}


class SearchHit(BaseModel):
    id: str
    video: str
    n: int
    frame_idx: int
    score: float
    thumb_url: str
    pts_time: float | None = None
    rank: int = 0
    # Chỉ có khi req.explain=True — giữ None để response nhẹ khi không cần.
    explain: HitExplain | None = None
    content: FrameContent | None = None


class SignalInfo(BaseModel):
    """1 dòng minh bạch: nhánh nào ĐÃ THẬT SỰ tham gia, trọng số bao nhiêu, dùng
    câu/từ khoá gì, ra bao nhiêu kết quả."""
    name: str
    weight: float
    query_text: str | None = None
    n_hits: int = 0


class BranchRanking(BaseModel):
    """Bảng xếp hạng RIÊNG của 1 nhánh (chưa gộp) — cho tab xem theo nhánh."""
    branch: str
    hits: list[SearchHit] = []


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    clauses_metaclip2: list[str]
    clauses_en: list[str]
    ocr_keywords: list[str] = []
    signals_used: list[SignalInfo] = []
    strict_filter_applied: bool = False
    strict_filter_pool_size: int | None = None
    # Minh bạch hoá thêm
    total_candidates: int = 0
    took_ms: int = 0
    branch_rankings: list[BranchRanking] = []
    cache_stats: dict | None = None

from pydantic import BaseModel

from api.schemas.search import FeedbackConfig, SearchHit, SignalConfig


class GapConstraint(BaseModel):
    """Ràng buộc khoảng cách THỜI GIAN giữa 2 sự kiện LIỀN KỀ — kiến thức con
    người có mà máy không có ("E2 phải xảy ra trong vòng 30 giây sau E1").
    Mạnh và cụ thể hơn hẳn một hệ số phạt λ chung cho cả chuỗi."""
    from_: int = 0
    to: int = 1
    min_s: float | None = None
    max_s: float | None = None

    model_config = {"populate_by_name": True}

    def __init__(self, **data):
        # Nhận cả "from" (từ khoá Python nên không đặt tên field trực tiếp được)
        if "from" in data:
            data["from_"] = data.pop("from")
        super().__init__(**data)


class TemporalRequest(BaseModel):
    events: list[str]
    context: str = ""
    topk: int = 100
    per_event: int = 1500

    # Bật/tắt HẲN việc tự động tách mệnh đề (LLM/heuristic) cho MỌI sự kiện chưa
    # có `clauses_override` riêng — False = mỗi sự kiện encode NGUYÊN câu làm 1
    # mệnh đề duy nhất, không gọi LLM tách. `clauses_override[i]` (nếu có) LUÔN
    # thắng cờ này cho sự kiện đó — quyết định thủ công không bao giờ bị cờ mặc
    # định này ghi đè.
    split_clauses: bool = True

    # Ghi đè chữ/lời RIÊNG từng sự kiện — người biết chính xác chữ trên màn hình
    # của MỘT khoảnh khắc thì tự nhập cho đúng khoảnh khắc đó, các sự kiện khác
    # vẫn dùng câu mô tả (không phải tất-cả-hoặc-không-gì).
    ocr_queries: list[str] | None = None
    asr_queries: list[str] | None = None

    # ĐÃ BỎ phạt khoảng cách thời gian (DANTE λ) theo yêu cầu — TRAKE không còn
    # giả định các sự kiện phải gần nhau về thời gian; luôn chạy với λ=0 ở
    # core.temporal.search_temporal. Không nhận trường lambda_penalty từ client
    # nữa (loại bỏ hẳn khỏi hợp đồng API để không ai vô tình bật lại).

    # Trọng số các nhánh thị giác góp vào điểm mỗi khung hình (KHÔNG đổi thuật
    # toán DP/boundary-anchor — chỉ đổi cách CHẤM ĐIỂM). Key: "metaclip2" (luôn
    # bật, mặc định weight=1.0) / "pecore" / "beit3" / "capemb" (mặc định tắt,
    # người dùng tự bật khi cần — cùng nguyên tắc với bàn trộn ở Search).
    signals: dict[str, SignalConfig] | None = None

    # 2 sự kiện làm NEO thị giác — mặc định đầu/cuối, nhưng cặp Ở GIỮA thường
    # đặc trưng và dễ nhận diện hơn.
    anchor_indices: list[int] | None = None

    # Thu hẹp phạm vi trước khi dò chuỗi.
    video_scope: list[str] | None = None

    # frame_idx người dùng ĐÃ TỰ TÌM RA và chắc chắn đúng, song song với `events`
    # (None = chưa khoá). Mỗi sự kiện khoá được làm không gian tìm kiếm co lại
    # đáng kể — đòn bẩy mạnh nhất cho chuỗi dài.
    locked_frames: list[int | None] | None = None

    gap_constraints: list[GapConstraint] | None = None

    # Số khung thay thế trả kèm cho MỖI vị trí sự kiện, để đổi nhanh một mắt xích
    # yếu mà không phải chạy lại toàn bộ.
    alternates_per_event: int = 0

    # Phản hồi liên quan (Rocchio) RIÊNG từng sự kiện — key = chỉ số sự kiện
    # (0-based, "0" = E1...). Đánh dấu ✓/✗ trên khung của sự kiện nào thì CHỈ
    # dịch vector của đúng sự kiện đó (mỗi sự kiện tìm 1 khoảnh khắc khác nhau
    # trong cùng video, không share ngữ nghĩa) — dùng chung core.fusion.rocchio
    # với /search, CHỈ đổi vector đầu vào trước DP, không đụng thuật toán.
    feedback: dict[int, FeedbackConfig] | None = None

    # Ghi đè tay mệnh đề đã tách CHO TỪNG sự kiện — key = chỉ số sự kiện, value
    # = danh sách câu mệnh đề TỰ VIẾT, thay hẳn cho việc gọi LLM tách tự động
    # (core.query_service.clauses_metaclip2) cho ĐÚNG sự kiện đó. Sự kiện không
    # có mặt trong dict này vẫn tách tự động như cũ — không phải tất-cả-hoặc-
    # không-gì, cùng nguyên tắc với ocr_queries/asr_queries. CHỈ đổi câu đưa vào
    # encode, không đụng gì DP/boundary-anchor phía sau.
    clauses_override: dict[int, list[str]] | None = None


class TemporalEventHit(SearchHit):
    alternates: list[SearchHit] = []


class TemporalCandidate(BaseModel):
    video: str
    total_score: float
    hits: list[TemporalEventHit]   # 1 hit/sự kiện, đúng thứ tự E1..En


class TemporalResponse(BaseModel):
    candidates: list[TemporalCandidate]
    # Mệnh đề THỰC SỰ đã dùng để encode cho từng sự kiện (sau khi tách, nếu có)
    # — cùng thứ tự với `events` gửi lên. Trước đây chạy hoàn toàn ngầm, không
    # có gì để người dùng xem/kiểm tra máy đang hiểu câu thế nào (khác Search,
    # nơi QueryPanel luôn hiện mệnh đề). event_clauses[i] == [events[i]] nghĩa
    # là sự kiện đó không tách được thêm (đã là 1 mệnh đề, hành vi cũ).
    event_clauses: list[list[str]] = []

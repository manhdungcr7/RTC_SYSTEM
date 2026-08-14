from pydantic import BaseModel

from api.schemas.search import SearchHit, SignalConfig


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


class TemporalEventHit(SearchHit):
    alternates: list[SearchHit] = []


class TemporalCandidate(BaseModel):
    video: str
    total_score: float
    hits: list[TemporalEventHit]   # 1 hit/sự kiện, đúng thứ tự E1..En


class TemporalResponse(BaseModel):
    candidates: list[TemporalCandidate]

"""Tầng truy cập Meilisearch — thay Elasticsearch (nhẹ hơn nhiều: không cần heap
JVM 1-2GB, có typo-tolerance + bỏ dấu tiếng Việt tự nhiên sẵn có, hợp máy dev RAM
hạn chế). 3 index: `aic_frames` (OCR/caption/objects theo khung hình), `aic_asr`
(lời thoại theo đoạn thời gian), `aic_videos` (mục 3 — lọc video trước: gộp
ASR+caption theo TỪNG VIDEO + thể loại kênh, xem indexing/build_video_index.py).

Khác ES 1 chỗ đáng chú ý: field `objects` KHÔNG còn ghép token "cls_grid_color"
làm 1 từ (Elasticsearch phải ghép vì whitespace-analyzer + phải dùng wildcard mới
tách được) — ở đây lưu 3 phần `cls`/`grid`/`color` là CÁC TỪ RIÊNG trong cùng field
(vd "bicycle 2a red"), tận dụng tokenizer từ-thật của Meilisearch, tra bằng full-
text search bình thường, không cần wildcard.

Giữ NGUYÊN chữ ký các hàm public gốc so với core/repositories/es_repo.py cũ —
tham số MỚI (videos/strict) đều có default an toàn, không phá code gọi cũ.
"""
from __future__ import annotations

import meilisearch

from config import settings


def _video_filter(videos: list[str] | None) -> str | None:
    if not videos:
        return None
    quoted = ", ".join(f'"{v}"' for v in videos)
    return f"video IN [{quoted}]"


def build_match_query(query_text: str, match: str) -> tuple[str, dict]:
    """Dịch chế độ khớp của người dùng sang cú pháp Meilisearch THẬT SỰ có.

    GIỚI HẠN THẬT (nói rõ để không hứa quá): Meilisearch KHÔNG cho chỉnh mức
    dung sai lỗi chính tả THEO TỪNG TRUY VẤN — `typoTolerance` là cài đặt cấp
    INDEX. Cái điều khiển được theo truy vấn là:
      - "phrase"   -> bọc ngoặc kép: khớp ĐÚNG CỤM liền nhau, KHÔNG dung sai typo.
                       Đây chính là đường "typo = 0" trên thực tế.
      - "contains" -> matchingStrategy="all": bắt buộc có ĐỦ MỌI TỪ (thứ tự tự do),
                       vẫn hưởng dung sai typo mặc định của index.
      - "prefix"   -> hành vi mặc định Meilisearch (khớp tiền tố ở từ cuối), lỏng nhất.
    """
    q = (query_text or "").strip()
    if not q:
        return "", {}
    if match == "phrase":
        # đã có ngoặc kép sẵn thì giữ nguyên, tránh bọc lồng thành ""..."" (Meili hiểu sai)
        if not (q.startswith('"') and q.endswith('"')):
            q = f'"{q}"'
        return q, {}
    if match == "prefix":
        return q, {}
    return q, {"matchingStrategy": "all"}   # "contains" (mặc định)


class MeiliRepo:
    def __init__(self, url: str = settings.MEILI_URL, api_key: str = settings.MEILI_KEY):
        self.client = meilisearch.Client(url, api_key or None)
        self.frames = self.client.index(settings.MEILI_INDEX_FRAMES)
        self.asr = self.client.index(settings.MEILI_INDEX_ASR)
        self.videos = self.client.index(settings.MEILI_INDEX_VIDEOS)

    def search_frames(self, field: str, query_text: str, size: int,
                       videos: list[str] | None = None, strict: bool = False) -> list[str]:
        """field ∈ {"ocr_text","objects","caption"}. Trả list id, sort theo điểm
        liên quan giảm dần. `videos`: TÙY CHỌN — giới hạn 1 tập video (mục 3, lọc
        video trước / mục 4, strict OCR filter theo video_scope)."""
        if not query_text or not query_text.strip():
            return []
        opts = {"attributesToSearchOn": [field], "limit": size}
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        if strict:
            opts["matchingStrategy"] = "all"
        res = self.frames.search(query_text, opts)
        return [hit["id"] for hit in res["hits"]]

    def search_frames_scored_global(self, field: str, query_text: str, size: int,
                                     videos: list[str] | None = None,
                                     strict: bool = False) -> dict[str, float]:
        """Giống search_frames() nhưng GIỮ điểm — dùng để phát hiện khớp OCR ĐỘ TIN
        CẬY CAO trên toàn kho (mục 4, strict_text_filter) chứ không giới hạn 1
        video như search_frames_scored() (TRAKE)."""
        if not query_text or not query_text.strip():
            return {}
        opts = {"attributesToSearchOn": [field], "limit": size, "showRankingScore": True}
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        if strict:
            opts["matchingStrategy"] = "all"
        res = self.frames.search(query_text, opts)
        return {hit["id"]: float(hit.get("_rankingScore", 0.0)) for hit in res["hits"]}

    def search_objects(self, query_text: str, size: int,
                        videos: list[str] | None = None) -> list[str]:
        """Tra field "objects" — lưu dạng TỪ RIÊNG (cls/grid/color tách nhau bằng
        khoảng trắng, vd "bicycle 2a red person 1a blue"), search từ thường là đủ
        (khác ES phải dùng wildcard vì token ghép "cls_grid_color")."""
        if not query_text or not query_text.strip():
            return []
        opts = {"attributesToSearchOn": ["objects"], "limit": size}
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        res = self.frames.search(query_text, opts)
        return [hit["id"] for hit in res["hits"]]

    def search_asr(self, query_text: str, size: int, videos: list[str] | None = None,
                    strict: bool = False) -> list[tuple[str, float, float, float]]:
        """Trả list (video, start, end, score), sort theo điểm liên quan giảm dần.
        `videos`/`strict`: xem search_frames()."""
        if not query_text or not query_text.strip():
            return []
        opts = {"attributesToSearchOn": ["text"], "limit": size, "showRankingScore": True}
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        if strict:
            opts["matchingStrategy"] = "all"
        res = self.asr.search(query_text, opts)
        return [(h["video"], float(h["start"]), float(h["end"]), float(h.get("_rankingScore", 0.0)))
                for h in res["hits"]]

    def search_frames_scored(self, field: str, query_text: str, video: str, size: int,
                              strict: bool = False) -> dict[str, float]:
        """Giống search_frames() nhưng GIỚI HẠN 1 video và GIỮ điểm — dùng cho
        core.temporal (DANTE DP). `strict=True` ép Meilisearch yêu cầu khớp TẤT CẢ
        từ trong câu (matchingStrategy="all") — mặc định Meilisearch chỉ cần khớp
        1 phần, nên câu "cắt nấm" có thể được tính điểm chỉ nhờ từ "cắt" khớp
        (xuất hiện ở MỌI banner "X CẮT Y" của MỌI nguyên liệu) dù không hề có
        "nấm" — ĐÃ ĐO THẬT gây điểm giả cao cho video sai trong TRAKE DP."""
        return self.search_frames_scored_global(field, query_text, size, videos=[video], strict=strict)

    def search_frames_scored_match(self, field: str, query_text: str, size: int,
                                    videos: list[str] | None = None,
                                    match: str = "contains") -> dict[str, float]:
        """Như search_frames_scored_global() nhưng nhận CHẾ ĐỘ KHỚP của người dùng
        (contains/phrase/prefix — xem build_match_query) thay vì cờ strict nhị phân."""
        q, extra = build_match_query(query_text, match)
        if not q:
            return {}
        opts = {"attributesToSearchOn": [field], "limit": size, "showRankingScore": True}
        opts.update(extra)
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        res = self.frames.search(q, opts)
        return {hit["id"]: float(hit.get("_rankingScore", 0.0)) for hit in res["hits"]}

    def search_asr_scored_match(self, query_text: str, size: int,
                                 videos: list[str] | None = None,
                                 match: str = "contains") -> list[tuple[str, float, float, float]]:
        """Như search_asr() nhưng theo chế độ khớp của người dùng."""
        q, extra = build_match_query(query_text, match)
        if not q:
            return []
        opts = {"attributesToSearchOn": ["text"], "limit": size, "showRankingScore": True}
        opts.update(extra)
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        res = self.asr.search(q, opts)
        return [(h["video"], float(h["start"]), float(h["end"]), float(h.get("_rankingScore", 0.0)))
                for h in res["hits"]]

    def search_objects_conds(self, conds: list[dict], size: int,
                              videos: list[str] | None = None) -> dict[str, float]:
        """Tra field "objects" theo các ĐIỀU KIỆN CÓ CẤU TRÚC (cls + màu, không
        còn vị trí lưới — bỏ vì ít tác dụng phân biệt, xem ObjectCond). Ghép
        thành cụm từ mà index đã lưu (các phần là TỪ RIÊNG trong cùng field, vd
        "bicycle red" — token vị trí "2a" vẫn còn trong dữ liệu đã index cũ,
        không tra tới nó không sao vì matchingStrategy="all" chỉ đòi các từ ta
        GỬI phải có mặt, không quan tâm từ khác trong field).

        Nhiều điều kiện -> yêu cầu khớp ĐỦ (matchingStrategy="all") vì người dùng
        đã chủ động thêm từng cái một, mỗi cái đều phải có mặt."""
        if not conds:
            return {}
        terms: list[str] = []
        for c in conds:
            cls = (c.get("cls") or "").strip()
            if not cls:
                continue
            terms.append(cls)
            color = (c.get("color") or "").strip()
            if color:
                terms.append(color)
        if not terms:
            return {}
        opts = {"attributesToSearchOn": ["objects"], "limit": size,
                "showRankingScore": True, "matchingStrategy": "all"}
        vf = _video_filter(videos)
        if vf:
            opts["filter"] = vf
        res = self.frames.search(" ".join(terms), opts)
        return {hit["id"]: float(hit.get("_rankingScore", 0.0)) for hit in res["hits"]}

    def get_frame_docs(self, ids: list[str]) -> dict[str, dict]:
        """Lấy caption/ocr_text/objects của 1 tập khung hình — để hiển thị NỘI
        DUNG ĐẦY ĐỦ ngay cạnh kết quả (đối chiếu nhanh, đặc biệt cho Q&A đọc chữ
        nhỏ) mà không phải mở video. Dùng filter theo id thay vì search để lấy
        chính xác. Áp dụng cho MỌI khung hình gọi tới, không chỉ hạng cao nhất —
        nơi gọi (search.py/temporal.py) quyết định gọi cho bao nhiêu khung."""
        if not ids:
            return {}
        out: dict[str, dict] = {}
        BATCH = 200
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            quoted = ", ".join(f'"{x}"' for x in chunk)
            try:
                res = self.frames.search("", {
                    "filter": f"id IN [{quoted}]",
                    "limit": len(chunk),
                    "attributesToRetrieve": ["id", "caption", "ocr_text", "objects"],
                })
            except Exception as e:
                # `id` có thể chưa nằm trong filterableAttributes -> bỏ qua êm,
                # UI chỉ mất phần nội dung phụ chứ không hỏng kết quả tìm kiếm.
                print(f"[meili_repo] get_frame_docs bỏ qua ({type(e).__name__}: {e})")
                return out
            for h in res["hits"]:
                out[h["id"]] = {"caption": h.get("caption"), "ocr": h.get("ocr_text"),
                                 "objects": h.get("objects")}
        return out

    def asr_segments_for_video(self, video: str, start: float, end: float,
                                size: int = 50) -> list[dict]:
        """Các đoạn lời thoại trong khoảng thời gian của 1 video — hiển thị "lời
        thoại quanh khung hình này" trong khung chi tiết."""
        try:
            res = self.asr.search("", {
                "filter": f'video = "{video}" AND end >= {start} AND start <= {end}',
                "limit": size,
                "attributesToRetrieve": ["start", "end", "text"],
            })
        except Exception as e:
            print(f"[meili_repo] asr_segments_for_video bỏ qua ({type(e).__name__}: {e})")
            return []
        segs = [{"t": float(h["start"]), "end": float(h["end"]), "text": h.get("text", "")}
                for h in res["hits"]]
        return sorted(segs, key=lambda s: s["t"])

    def all_asr_for_video(self, video: str, size: int = 2000) -> list[dict]:
        """Toàn bộ transcript của 1 video — cho Video Workbench."""
        try:
            res = self.asr.search("", {
                "filter": f'video = "{video}"', "limit": size,
                "attributesToRetrieve": ["start", "end", "text"],
            })
        except Exception as e:
            print(f"[meili_repo] all_asr_for_video bỏ qua ({type(e).__name__}: {e})")
            return []
        segs = [{"t": float(h["start"]), "end": float(h["end"]), "text": h.get("text", "")}
                for h in res["hits"]]
        return sorted(segs, key=lambda s: s["t"])

    def all_ocr_for_video(self, video: str, size: int = 2000) -> list[dict]:
        """Toàn bộ chữ trên hình của 1 video theo thứ tự khung — cho Workbench."""
        try:
            res = self.frames.search("", {
                "filter": f'video = "{video}"', "limit": size,
                "attributesToRetrieve": ["n", "ocr_text"],
            })
        except Exception as e:
            print(f"[meili_repo] all_ocr_for_video bỏ qua ({type(e).__name__}: {e})")
            return []
        rows = [{"n": int(h["n"]), "text": (h.get("ocr_text") or "").strip()}
                for h in res["hits"] if (h.get("ocr_text") or "").strip()]
        return sorted(rows, key=lambda r: r["n"])

    def search_asr_in_video(self, video: str, query_text: str, size: int,
                             strict: bool = False) -> list[tuple[float, float, float]]:
        """Giống search_asr() nhưng GIỚI HẠN 1 video — trả (start, end, score).
        `strict`: xem search_frames_scored()."""
        segs = self.search_asr(query_text, size, videos=[video], strict=strict)
        return [(start, end, score) for _, start, end, score in segs]

    # ---- aic_videos: lọc video trước (mục 3) ----

    def search_videos(self, query_text: str, size: int,
                       category: str | None = None,
                       field: str = "all") -> list[tuple[str, float]]:
        """Tìm/duyệt VIDEO (không phải khung hình) + lọc tuỳ chọn theo `category`
        (bảng SHARD_CATEGORY_MAP). Trả list (video, score) giảm dần.
        query_text rỗng + có category -> trả TOÀN BỘ video thuộc category (duyệt
        theo thể loại, không cần gõ chữ).

        `field` — NGUỒN nội dung để khớp:
          "all"     : tiêu đề + lời thoại + mô tả cảnh (MẶC ĐỊNH, rộng nhất)
          "asr"     : CHỈ lời thoại — dùng khi biết manh mối nằm ở lời nói
          "caption" : CHỈ mô tả cảnh — dùng khi manh mối nằm ở hình ảnh
        Chọn 1 nguồn là HẸP HƠN "all": đúng khi bạn biết manh mối ở đâu, nhưng
        sẽ bỏ sót nếu đoán sai — nên mặc định vẫn là "all"."""
        attrs = {"asr": ["asr_text"], "caption": ["caption_text"]}.get(
            field, ["text", "title"])
        opts = {"attributesToSearchOn": attrs, "limit": size, "showRankingScore": True}
        if category:
            opts["filter"] = f'category = "{category}"'
        if not query_text or not query_text.strip():
            if not category:
                return []
            res = self.videos.search("", opts)
        else:
            res = self.videos.search(query_text, opts)
        return [(h["video"], float(h.get("_rankingScore", 1.0))) for h in res["hits"]]

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

    def search_asr_in_video(self, video: str, query_text: str, size: int,
                             strict: bool = False) -> list[tuple[float, float, float]]:
        """Giống search_asr() nhưng GIỚI HẠN 1 video — trả (start, end, score).
        `strict`: xem search_frames_scored()."""
        segs = self.search_asr(query_text, size, videos=[video], strict=strict)
        return [(start, end, score) for _, start, end, score in segs]

    # ---- aic_videos: lọc video trước (mục 3) ----

    def search_videos(self, query_text: str, size: int,
                       category: str | None = None) -> list[tuple[str, float]]:
        """Tra field "text" (ASR+caption gộp theo video, xem
        indexing/build_video_index.py) + lọc tuỳ chọn theo `category` (tên kênh
        YouTube — proxy cho thể loại, xem core.config.VIDEO_CATEGORY_MAP). Trả
        list (video, score) giảm dần. query_text rỗng + có category -> trả TOÀN
        BỘ video thuộc category đó (browse theo thể loại, không cần gõ chữ)."""
        opts = {"attributesToSearchOn": ["text", "title"], "limit": size, "showRankingScore": True}
        if category:
            opts["filter"] = f'category = "{category}"'
        if not query_text or not query_text.strip():
            if not category:
                return []
            res = self.videos.search("", opts)
        else:
            res = self.videos.search(query_text, opts)
        return [(h["video"], float(h.get("_rankingScore", 1.0))) for h in res["hits"]]

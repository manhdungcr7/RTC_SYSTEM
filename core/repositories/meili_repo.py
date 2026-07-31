"""Tầng truy cập Meilisearch — thay Elasticsearch (nhẹ hơn nhiều: không cần heap
JVM 1-2GB, có typo-tolerance + bỏ dấu tiếng Việt tự nhiên sẵn có, hợp máy dev RAM
hạn chế). 2 index: `aic_frames` (OCR/caption/objects theo khung hình) + `aic_asr`
(lời thoại theo đoạn thời gian) — xem indexing/build_meili.py.

Khác ES 1 chỗ đáng chú ý: field `objects` KHÔNG còn ghép token "cls_grid_color"
làm 1 từ (Elasticsearch phải ghép vì whitespace-analyzer + phải dùng wildcard mới
tách được) — ở đây lưu 3 phần `cls`/`grid`/`color` là CÁC TỪ RIÊNG trong cùng field
(vd "bicycle 2a red"), tận dụng tokenizer từ-thật của Meilisearch, tra bằng full-
text search bình thường, không cần wildcard.

Giữ NGUYÊN chữ ký các hàm public so với core/repositories/es_repo.py cũ.
"""
from __future__ import annotations

import meilisearch

from config import settings


class MeiliRepo:
    def __init__(self, url: str = settings.MEILI_URL, api_key: str = settings.MEILI_KEY):
        self.client = meilisearch.Client(url, api_key or None)
        self.frames = self.client.index(settings.MEILI_INDEX_FRAMES)
        self.asr = self.client.index(settings.MEILI_INDEX_ASR)

    def search_frames(self, field: str, query_text: str, size: int) -> list[str]:
        """field ∈ {"ocr_text","objects","caption"}. Trả list id, sort theo điểm
        liên quan giảm dần."""
        if not query_text or not query_text.strip():
            return []
        res = self.frames.search(query_text, {
            "attributesToSearchOn": [field], "limit": size,
        })
        return [hit["id"] for hit in res["hits"]]

    def search_objects(self, query_text: str, size: int) -> list[str]:
        """Tra field "objects" — lưu dạng TỪ RIÊNG (cls/grid/color tách nhau bằng
        khoảng trắng, vd "bicycle 2a red person 1a blue"), search từ thường là đủ
        (khác ES phải dùng wildcard vì token ghép "cls_grid_color")."""
        if not query_text or not query_text.strip():
            return []
        res = self.frames.search(query_text, {
            "attributesToSearchOn": ["objects"], "limit": size,
        })
        return [hit["id"] for hit in res["hits"]]

    def search_asr(self, query_text: str, size: int) -> list[tuple[str, float, float, float]]:
        """Trả list (video, start, end, score), sort theo điểm liên quan giảm dần."""
        if not query_text or not query_text.strip():
            return []
        res = self.asr.search(query_text, {
            "attributesToSearchOn": ["text"], "limit": size, "showRankingScore": True,
        })
        return [(h["video"], float(h["start"]), float(h["end"]), float(h.get("_rankingScore", 0.0)))
                for h in res["hits"]]

    def search_frames_scored(self, field: str, query_text: str, video: str, size: int) -> dict[str, float]:
        """Giống search_frames() nhưng GIỚI HẠN 1 video và GIỮ điểm — dùng cho
        core.temporal (DANTE DP)."""
        if not query_text or not query_text.strip():
            return {}
        res = self.frames.search(query_text, {
            "attributesToSearchOn": [field], "filter": f'video = "{video}"',
            "limit": size, "showRankingScore": True,
        })
        return {hit["id"]: float(hit.get("_rankingScore", 0.0)) for hit in res["hits"]}

    def search_asr_in_video(self, video: str, query_text: str, size: int) -> list[tuple[float, float, float]]:
        """Giống search_asr() nhưng GIỚI HẠN 1 video — trả (start, end, score)."""
        if not query_text or not query_text.strip():
            return []
        res = self.asr.search(query_text, {
            "attributesToSearchOn": ["text"], "filter": f'video = "{video}"',
            "limit": size, "showRankingScore": True,
        })
        return [(float(h["start"]), float(h["end"]), float(h.get("_rankingScore", 0.0)))
                for h in res["hits"]]

"""Tầng truy cập Elasticsearch — OCR/objects/caption (`aic_frames`) + ASR
(`aic_asr`). `search_frames()` trả rank-list id giống `milvus_repo.search()` (đúng
dạng `core.fusion.rrf()` cần). `aic_asr` KHÔNG có sẵn theo keyframe — trả đoạn
(video,start,end,score), align sang keyframe ở `core/asr_align.py`.
"""
from __future__ import annotations

from elasticsearch import Elasticsearch

from config import settings


class EsRepo:
    def __init__(self, url: str = settings.ES_URL):
        self.es = Elasticsearch(url)

    def search_frames(self, field: str, query_text: str, size: int) -> list[str]:
        """field ∈ {"ocr_text","objects","caption"}. Trả list id "{video}:{n:06d}",
        sort theo BM25 _score giảm dần."""
        if not query_text or not query_text.strip():
            return []
        res = self.es.search(
            index=settings.ES_INDEX_FRAMES,
            query={"match": {field: query_text}},
            size=size,
            _source=False,
        )
        return [hit["_id"] for hit in res["hits"]["hits"]]

    def search_objects(self, query_text: str, size: int) -> list[str]:
        """Tra field "objects" — token index dạng GHÉP "cls_grid_color" (vd
        "bicycle_2a_red", whitespace analyzer KHÔNG tách dấu "_"), nên match query
        thường ("bicycle") sẽ KHÔNG khớp bất kỳ token nào (chỉ khớp token y hệt
        "bicycle_2a_red"). Dùng wildcard *từ* cho MỖI từ trong câu để bắt được lớp/
        màu nằm trong token ghép, dù chậm hơn match thường (chấp nhận được — field
        nhỏ, chỉ chạy khi người dùng chủ động nhập/câu có cue màu)."""
        if not query_text or not query_text.strip():
            return []
        words = [w.lower() for w in query_text.split() if w.strip()]
        if not words:
            return []
        should = [{"wildcard": {"objects": {"value": f"*{w}*"}}} for w in words]
        res = self.es.search(
            index=settings.ES_INDEX_FRAMES,
            query={"bool": {"should": should, "minimum_should_match": 1}},
            size=size,
            _source=False,
        )
        return [hit["_id"] for hit in res["hits"]["hits"]]

    def search_asr(self, query_text: str, size: int) -> list[tuple[str, float, float, float]]:
        """Trả list (video, start, end, es_score), sort theo _score giảm dần."""
        if not query_text or not query_text.strip():
            return []
        res = self.es.search(
            index=settings.ES_INDEX_ASR,
            query={"match": {"text": query_text}},
            size=size,
        )
        out = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            out.append((src["video"], float(src["start"]), float(src["end"]), float(hit["_score"])))
        return out

    def search_frames_scored(self, field: str, query_text: str, video: str, size: int) -> dict[str, float]:
        """Giống search_frames() nhưng GIỚI HẠN 1 video và GIỮ điểm BM25 thật —
        dùng cho core.temporal (DANTE DP cần điểm số/keyframe, không chỉ rank)."""
        if not query_text or not query_text.strip():
            return {}
        res = self.es.search(
            index=settings.ES_INDEX_FRAMES,
            query={"bool": {"must": [{"match": {field: query_text}}],
                             "filter": [{"term": {"video": video}}]}},
            size=size,
            _source=False,
        )
        return {hit["_id"]: float(hit["_score"]) for hit in res["hits"]["hits"]}

    def search_asr_in_video(self, video: str, query_text: str, size: int) -> list[tuple[float, float, float]]:
        """Giống search_asr() nhưng GIỚI HẠN 1 video — trả (start, end, score)."""
        if not query_text or not query_text.strip():
            return []
        res = self.es.search(
            index=settings.ES_INDEX_ASR,
            query={"bool": {"must": [{"match": {"text": query_text}}],
                             "filter": [{"term": {"video": video}}]}},
            size=size,
        )
        return [(float(h["_source"]["start"]), float(h["_source"]["end"]), float(h["_score"]))
                for h in res["hits"]["hits"]]

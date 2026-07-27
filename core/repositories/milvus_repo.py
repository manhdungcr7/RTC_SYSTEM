"""Tầng truy cập Milvus — mọi nơi khác trong core/api KHÔNG gọi thẳng pymilvus.

Mỗi collection (metaclip2/beit3/pecore/dinov3/capemb) có schema giống nhau:
id(VARCHAR32 PK "{video}:{n:06d}"), video, n, frame_idx, vector — xem
indexing/load_to_milvus.py. `search()` trả RANK LIST id (đã sort theo điểm giảm
dần) — đúng dạng `core.fusion.rrf()` cần, không cần ma trận điểm toàn cục.
"""
from __future__ import annotations

import numpy as np
from pymilvus import MilvusClient

from config import settings


class MilvusRepo:
    def __init__(self, uri: str = settings.MILVUS_URI):
        self.client = MilvusClient(uri=uri)

    def search(self, collection: str, vector: np.ndarray, topk: int,
               video_filter: str | None = None) -> list[str]:
        """1 vector query -> list id, sort theo cosine giảm dần."""
        filter_expr = f'video == "{video_filter}"' if video_filter else None
        res = self.client.search(
            collection_name=collection,
            data=[vector.astype(np.float32).tolist()],
            limit=topk,
            filter=filter_expr,
            output_fields=["id"],
        )
        return [hit["entity"]["id"] for hit in res[0]]

    def search_many(self, collection: str, vectors: np.ndarray, topk: int) -> list[list[str]]:
        """Nhiều vector query (vd nhiều mệnh đề) trong 1 lần gọi Milvus -> list rank-list."""
        res = self.client.search(
            collection_name=collection,
            data=vectors.astype(np.float32).tolist(),
            limit=topk,
            output_fields=["id"],
        )
        return [[hit["entity"]["id"] for hit in row] for row in res]

    def search_many_scored(self, collection: str, vectors: np.ndarray,
                            topk: int) -> list[list[tuple[str, float]]]:
        """Giống search_many() nhưng giữ điểm cosine — dùng cho maxmean đa mệnh đề
        (core.fusion.maxmean_clauses), cần điểm thật để tính max+alpha*mean."""
        res = self.client.search(
            collection_name=collection,
            data=vectors.astype(np.float32).tolist(),
            limit=topk,
            output_fields=["id"],
        )
        return [[(hit["entity"]["id"], float(hit["distance"])) for hit in row] for row in res]

    def search_scored(self, collection: str, vector: np.ndarray, topk: int) -> list[tuple[str, float]]:
        """Giống search() nhưng giữ cả điểm cosine — dùng khi cần điểm thật (vd /similar)."""
        res = self.client.search(
            collection_name=collection,
            data=[vector.astype(np.float32).tolist()],
            limit=topk,
            output_fields=["id"],
        )
        return [(hit["entity"]["id"], float(hit["distance"])) for hit in res[0]]

    def fetch_video_vectors(self, collection: str, video: str):
        """Toàn bộ vector của 1 video, SẮP theo `n` tăng dần (= thứ tự thời gian) —
        dùng cho DANTE DP trong core/temporal.py (1 video chỉ ~100-300 keyframe nên
        query() là đủ nhẹ, không cần search()). Trả (ids, ns, frame_idxs, vectors[K,D])."""
        rows = self.client.query(
            collection_name=collection,
            filter=f'video == "{video}"',
            output_fields=["id", "n", "frame_idx", "vector"],
            limit=10000,
        )
        rows.sort(key=lambda r: r["n"])
        ids = [r["id"] for r in rows]
        ns = [int(r["n"]) for r in rows]
        frame_idxs = [int(r["frame_idx"]) for r in rows]
        vecs = np.array([r["vector"] for r in rows], dtype=np.float32)
        return ids, ns, frame_idxs, vecs

    def fetch_by_ids(self, collection: str, ids: list[str]) -> dict[str, tuple[str, int, int]]:
        """Hydrate metadata (video,n,frame_idx) cho 1 danh sách id đã có (vd sau khi
        RRF fusion đã chọn ra top-N ứng viên) — 1 lần gọi Milvus duy nhất, id nào
        cũng tra được ở BẤT KỲ collection nào (video/n/frame_idx giống nhau ở cả 5)."""
        if not ids:
            return {}
        id_list = ", ".join(f'"{i}"' for i in ids)
        rows = self.client.query(
            collection_name=collection,
            filter=f'id in [{id_list}]',
            output_fields=["id", "video", "n", "frame_idx"],
            limit=len(ids),
        )
        return {r["id"]: (r["video"], int(r["n"]), int(r["frame_idx"])) for r in rows}

    def videos_from_topk(self, collection: str, vector: np.ndarray, per_event: int) -> list[str]:
        """Danh sách video (đã dedup) xuất hiện trong top-per_event của 1 vector —
        GIỮ THỨ TỰ theo rank (video của keyframe hạng cao đứng trước) để caller có
        thể CẮT BỚT an toàn (giữ video liên quan nhất) thay vì cắt ngẫu nhiên như
        set không thứ tự — dùng cho boundary-anchor TRAKE (core/temporal.py)."""
        res = self.client.search(
            collection_name=collection,
            data=[vector.astype(np.float32).tolist()],
            limit=per_event,
            output_fields=["video"],
        )
        videos = [hit["entity"]["video"] for hit in res[0]]
        return list(dict.fromkeys(videos))

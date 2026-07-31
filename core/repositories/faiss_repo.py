"""Tầng truy cập FAISS — thay Milvus (máy dev RAM không đủ để Milvus + etcd +
MinIO chạy ổn định, xem lý do đo thật trong hội thoại: Milvus báo "healthy" dù
nội bộ đã OOM "Cannot allocate memory"). Ở quy mô AIC (167,850 vector/nhánh),
FAISS `IndexFlatIP` (cosine chính xác tuyệt đối, vì vector đã chuẩn hoá đơn vị
lúc encode) chạy trong-process, không cần server riêng, đủ nhanh (vài ms/query).

Layout trên đĩa (xem indexing/build_faiss.py):
  <faiss_dir>/<branch>/index.faiss   — FAISS IndexFlatIP, N dòng
  <faiss_dir>/<branch>/meta.parquet  — N dòng, CÙNG THỨ TỰ với index (row i <-> vị
                                        trí i trong index), cột id/video/n/frame_idx

Giữ NGUYÊN chữ ký các hàm public so với core/repositories/milvus_repo.py cũ —
core/fusion.py, core/temporal.py, api/routers/* không cần sửa gì ngoài đổi import.
"""
from __future__ import annotations

from pathlib import Path

import faiss
import numpy as np
import pandas as pd


class FaissRepo:
    def __init__(self, faiss_dir: Path, enabled_branches: dict[str, bool] | None = None):
        self.faiss_dir = Path(faiss_dir)
        self._indices: dict[str, faiss.Index] = {}
        self._meta: dict[str, pd.DataFrame] = {}
        self._id_pos: dict[str, dict[str, int]] = {}
        self._video_pos: dict[str, dict[str, list[int]]] = {}
        for branch_dir in sorted(self.faiss_dir.iterdir()):
            branch = branch_dir.name
            if enabled_branches is not None and not enabled_branches.get(branch, False):
                continue
            self._load_branch(branch)

    def _load_branch(self, branch: str):
        idx_path = self.faiss_dir / branch / "index.faiss"
        meta_path = self.faiss_dir / branch / "meta.parquet"
        if not idx_path.exists() or not meta_path.exists():
            print(f"[faiss_repo] bỏ qua '{branch}' — thiếu file index/meta ({idx_path})")
            return
        idx = faiss.read_index(str(idx_path))
        meta = pd.read_parquet(meta_path)
        assert idx.ntotal == len(meta), \
            f"'{branch}': index.faiss có {idx.ntotal} dòng nhưng meta.parquet có {len(meta)} dòng — lệch nhau"
        self._indices[branch] = idx
        self._meta[branch] = meta
        self._id_pos[branch] = {doc_id: i for i, doc_id in enumerate(meta["id"].values)}
        video_pos: dict[str, list[int]] = {}
        ns = meta["n"].values
        for i, v in enumerate(meta["video"].values):
            video_pos.setdefault(v, []).append(i)
        for v, positions in video_pos.items():
            positions.sort(key=lambda p: ns[p])
        self._video_pos[branch] = video_pos
        print(f"[faiss_repo] nạp '{branch}': {idx.ntotal:,} vector, dim={idx.d}")

    # ---- API giữ nguyên chữ ký so với MilvusRepo cũ ----

    def search(self, collection: str, vector: np.ndarray, topk: int,
               video_filter: str | None = None) -> list[str]:
        if video_filter is not None:
            raise NotImplementedError("FaissRepo.search: video_filter chưa cần dùng ở codebase hiện tại")
        return [doc_id for doc_id, _ in self.search_scored(collection, vector, topk)]

    def search_many(self, collection: str, vectors: np.ndarray, topk: int) -> list[list[str]]:
        return [[doc_id for doc_id, _ in row] for row in self.search_many_scored(collection, vectors, topk)]

    def search_many_scored(self, collection: str, vectors: np.ndarray,
                            topk: int) -> list[list[tuple[str, float]]]:
        idx = self._indices[collection]
        ids = self._meta[collection]["id"].values
        topk = min(topk, idx.ntotal)
        dist, pos = idx.search(np.ascontiguousarray(vectors, dtype=np.float32), topk)
        out = []
        for row_pos, row_dist in zip(pos, dist):
            out.append([(ids[p], float(d)) for p, d in zip(row_pos, row_dist) if p != -1])
        return out

    def search_scored(self, collection: str, vector: np.ndarray, topk: int) -> list[tuple[str, float]]:
        return self.search_many_scored(collection, vector.reshape(1, -1), topk)[0]

    def fetch_video_vectors(self, collection: str, video: str):
        """Toàn bộ vector của 1 video, SẮP theo `n` tăng dần — dùng cho DANTE DP.
        Trả (ids, ns, frame_idxs, vectors[K,D])."""
        idx = self._indices[collection]
        meta = self._meta[collection]
        positions = self._video_pos[collection].get(video, [])
        if not positions:
            return [], [], [], np.zeros((0, idx.d), dtype=np.float32)
        ids = meta["id"].values
        ns = meta["n"].values
        frame_idxs = meta["frame_idx"].values
        vecs = np.stack([idx.reconstruct(int(p)) for p in positions]).astype(np.float32)
        return ([ids[p] for p in positions], [int(ns[p]) for p in positions],
                [int(frame_idxs[p]) for p in positions], vecs)

    def fetch_by_ids(self, collection: str, ids: list[str]) -> dict[str, tuple[str, int, int]]:
        if not ids:
            return {}
        meta = self._meta[collection]
        id_pos = self._id_pos[collection]
        out = {}
        for doc_id in ids:
            p = id_pos.get(doc_id)
            if p is None:
                continue
            row = meta.iloc[p]
            out[doc_id] = (row["video"], int(row["n"]), int(row["frame_idx"]))
        return out

    def fetch_vector_by_id(self, collection: str, doc_id: str) -> np.ndarray | None:
        """Thay `milvus.client.query(filter='id == ...')` cũ — dùng ở /similar để
        lấy lại vector dinov3 của 1 khung hình đã index sẵn (không cần encode lại)."""
        p = self._id_pos[collection].get(doc_id)
        if p is None:
            return None
        return self._indices[collection].reconstruct(int(p)).astype(np.float32)

    def videos_from_topk(self, collection: str, vector: np.ndarray, per_event: int) -> list[str]:
        """Danh sách video (dedup, GIỮ THỨ TỰ rank) trong top-per_event — dùng cho
        boundary-anchor TRAKE."""
        idx = self._indices[collection]
        meta = self._meta[collection]
        topk = min(per_event, idx.ntotal)
        _, pos = idx.search(vector.astype(np.float32).reshape(1, -1), topk)
        videos = meta["video"].values
        seen: set[str] = set()
        out = []
        for p in pos[0]:
            if p == -1:
                continue
            v = videos[p]
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

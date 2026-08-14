"""Hai tầng cache cho đường truy vấn — ĐIỀU KIỆN SỐNG CÒN của triết lý "người
dùng chủ động điều khiển" (mục 0 bản thiết kế): nếu mỗi lần kéo fader trọng số
phải chờ encode lại qua Kaggle (~1-3s/câu) thì KHÔNG AI chỉnh trọng số cả, và
cả bàn trộn tín hiệu trở thành vô dụng trên thực tế.

TẦNG 1 — cache VECTOR truy vấn (bền qua restart, lưu đĩa):
  key = (branch, text) -> vector đã encode.
  Cùng 1 câu truy vấn được chạy lại rất nhiều lần trong lúc thi (đổi trọng số,
  đổi phạm vi video, bật/tắt nhánh khác) — không có lý do gì gọi lại GPU Kaggle.
  Lưu đĩa để sống sót qua restart container / mất phiên Kaggle (đây cũng là lưới
  an toàn khi encoder chết giữa cuộc thi: câu đã tìm vẫn tra lại được).

TẦNG 2 — cache KẾT QUẢ TỪNG NHÁNH (chỉ RAM, theo phiên chạy):
  key = (branch, vector_hash, scope_hash, topk) -> [(id, điểm thô)].
  Khi người dùng CHỈ đổi trọng số gộp (không đổi câu/phạm vi), toàn bộ phần
  nặng (FAISS search / Meilisearch) đã có sẵn — chỉ cần gộp lại RRF, phản hồi
  dưới ~50ms. Đây chính là thứ khiến việc kéo fader trở nên tức thì.
"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np

from config import settings

VEC_CACHE_DIR = settings.ARTIFACTS_ROOT / "query_vec_cache"
BRANCH_CACHE_MAX = 512          # số entry giữ trong RAM (mỗi entry ~vài trăm dòng)
VEC_MEM_CACHE_MAX = 2048


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def vector_hash(vec: np.ndarray) -> str:
    """Hash NỘI DUNG vector — dùng làm khoá tầng 2. Không dùng hash của câu chữ
    vì cùng 1 câu qua 2 nhánh khác nhau ra 2 vector khác nhau, và vì vector có
    thể đến từ nguồn KHÔNG phải câu chữ (ảnh tham chiếu, Rocchio đã dịch chuyển)."""
    return hashlib.sha256(np.ascontiguousarray(vec, dtype=np.float32).tobytes()).hexdigest()[:32]


class QueryVectorCache:
    """Tầng 1 — bền qua restart. Mỗi vector 1 file .npy nhỏ (1024-2560 float32
    = 4-10KB); vài nghìn câu truy vấn cả cuộc thi vẫn chỉ vài chục MB."""

    def __init__(self, root: Path = VEC_CACHE_DIR):
        self.root = Path(root)
        self._mem: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _path(self, branch: str, text: str) -> Path:
        key = _hash(branch, text)
        # chia 2 cấp thư mục theo 2 ký tự đầu — tránh 1 thư mục hàng vạn file
        return self.root / branch / key[:2] / f"{key}.npy"

    def get(self, branch: str, text: str) -> np.ndarray | None:
        key = _hash(branch, text)
        with self._lock:
            v = self._mem.get(key)
            if v is not None:
                self._mem.move_to_end(key)
                self.hits += 1
                return v
        p = self._path(branch, text)
        if p.exists():
            try:
                v = np.load(p).astype(np.float32)
            except Exception:
                return None       # file hỏng -> coi như miss, sẽ encode lại và ghi đè
            with self._lock:
                self._mem[key] = v
                self._mem.move_to_end(key)
                while len(self._mem) > VEC_MEM_CACHE_MAX:
                    self._mem.popitem(last=False)
                self.hits += 1
            return v
        with self._lock:
            self.misses += 1
        return None

    def put(self, branch: str, text: str, vec: np.ndarray):
        key = _hash(branch, text)
        vec = np.ascontiguousarray(vec, dtype=np.float32)
        with self._lock:
            self._mem[key] = vec
            self._mem.move_to_end(key)
            while len(self._mem) > VEC_MEM_CACHE_MAX:
                self._mem.popitem(last=False)
        p = self._path(branch, text)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            np.save(p, vec)
        except Exception as e:
            # Cache hỏng KHÔNG được làm chết truy vấn — chỉ mất lợi ích tốc độ.
            print(f"[query_cache] không ghi được cache vector ({type(e).__name__}: {e})")

    def encode_cached(self, branch: str, texts: list[str], encode_fn) -> np.ndarray:
        """Encode 1 danh sách câu, CHỈ gọi `encode_fn` cho những câu chưa có cache.
        `encode_fn(list[str]) -> np.ndarray (n, D)` — đúng interface .encode() của
        mọi encoder trong core/query_encoders.py."""
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        cached: list[np.ndarray | None] = [self.get(branch, t) for t in texts]
        missing_idx = [i for i, v in enumerate(cached) if v is None]
        if missing_idx:
            fresh = encode_fn([texts[i] for i in missing_idx])
            for slot, i in enumerate(missing_idx):
                v = np.asarray(fresh[slot], dtype=np.float32)
                cached[i] = v
                self.put(branch, texts[i], v)
        return np.stack([c for c in cached if c is not None]).astype(np.float32)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
                "in_memory": len(self._mem)}


class BranchResultCache:
    """Tầng 2 — chỉ RAM. Giữ kết quả thô từng nhánh để đổi trọng số không phải
    chạy lại FAISS/Meilisearch."""

    def __init__(self, maxsize: int = BRANCH_CACHE_MAX):
        self._d: OrderedDict[str, list[tuple[str, float]]] = OrderedDict()
        self._lock = threading.Lock()
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(branch: str, vec_or_text_hash: str, scope_hash: str, topk: int, extra: str = "") -> str:
        return _hash(branch, vec_or_text_hash, scope_hash, str(topk), extra)

    def get(self, key: str) -> list[tuple[str, float]] | None:
        with self._lock:
            v = self._d.get(key)
            if v is not None:
                self._d.move_to_end(key)
                self.hits += 1
                return v
            self.misses += 1
            return None

    def put(self, key: str, value: list[tuple[str, float]]):
        with self._lock:
            self._d[key] = value
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def get_or_compute(self, key: str, compute_fn) -> list[tuple[str, float]]:
        v = self.get(key)
        if v is not None:
            return v
        v = compute_fn()
        self.put(key, v)
        return v

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
                "entries": len(self._d)}


def scope_signature(video_scope: list[str] | None, candidate_ids: set[str] | None) -> str:
    """Chữ ký ổn định cho "phạm vi tìm kiếm" — 2 request cùng câu nhưng khác phạm
    vi PHẢI ra khoá cache khác nhau. Dùng hash thay vì nối chuỗi vì tập id có thể
    lên tới hàng nghìn phần tử."""
    if candidate_ids is not None:
        return "cand:" + hashlib.sha256(
            "\x00".join(sorted(candidate_ids)).encode("utf-8")).hexdigest()[:32]
    if video_scope:
        return "vids:" + hashlib.sha256(
            "\x00".join(sorted(video_scope)).encode("utf-8")).hexdigest()[:32]
    return "all"

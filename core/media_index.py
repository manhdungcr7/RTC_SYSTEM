"""Thay `system/aic/data.py` (KeyframeIndex đọc từ .npz trong RAM) — vì giờ
metadata/vector đã ở FAISS, media_index chỉ cần trỏ tới FILE THẬT trên đĩa cho
tầng phục vụ (`api/routers/media.py`): ảnh keyframe (.webp), map frame_idx/pts_time
(CSV), video gốc (.mp4). Build 1 LẦN lúc FastAPI startup, giữ trong RAM.

Layout đĩa THẬT (2 kiểu khác nhau, glob đệ quy để không cần biết trước):
  data/raw_L21_a/out/keyframes/<video>/<n:06d>.webp                 (phẳng)
  data/raw_account0/out/L22_a/keyframes/<video>/<n:06d>.webp        (có sub-batch)
  .../maps/<video>.csv  cột: n,frame_idx,pts_time,fps  (THỨ TỰ CỘT khác data.py cũ!)
  data/videos_full/videos/<video>.mp4
"""
from __future__ import annotations

import csv
import glob
from pathlib import Path

from config import settings


class MediaIndex:
    def __init__(self):
        self._keyframe_dirs: dict[str, Path] = {}
        self._maps_csv: dict[str, Path] = {}
        self._mp4: dict[str, Path] = {}
        self._pts_cache: dict[str, dict[int, float]] = {}
        self._full_map_cache: dict[str, list[dict]] = {}

    def build(self) -> "MediaIndex":
        for d in glob.glob(str(settings.DATA_ROOT / settings.KEYFRAME_GLOB), recursive=True):
            p = Path(d)
            if p.is_dir():
                self._keyframe_dirs[p.name] = p

        for f in glob.glob(str(settings.DATA_ROOT / settings.MAPS_GLOB), recursive=True):
            p = Path(f)
            self._maps_csv[p.stem] = p

        if settings.VIDEOS_DIR.is_dir():
            for f in settings.VIDEOS_DIR.glob("*.mp4"):
                self._mp4[f.stem] = f

        print(f"[media_index] {len(self._keyframe_dirs):,} thư mục keyframe, "
              f"{len(self._maps_csv):,} maps CSV, {len(self._mp4):,} video mp4")
        return self

    def resolve_frame_path(self, video: str, n: int) -> Path | None:
        d = self._keyframe_dirs.get(video)
        if d is None:
            return None
        p = d / f"{n:06d}.webp"
        return p if p.exists() else None

    def resolve_thumb_path(self, video: str, n: int) -> Path | None:
        """Ban 320px tien sinh (xem indexing/build_thumbnails.py) — luoi ket qua
        dung ban nay thay vi anh goc de tai nhanh (xem SYSTEM_DESIGN thap thumbnail).
        Fallback ve anh goc neu chua tien sinh (vd chay lan dau chua build)."""
        p = settings.DATA_ROOT / "thumbs_320" / video / f"{n:06d}.webp"
        if p.exists():
            return p
        return self.resolve_frame_path(video, n)

    def resolve_video_path(self, video: str) -> Path | None:
        return self._mp4.get(video)

    def _load_full_map(self, video: str) -> list[dict]:
        """Bảng map ĐẦY ĐỦ của 1 video: [{n, frame_idx, pts_time, fps}] sort theo n.
        Đây là NGUỒN CHÂN LÝ để quy đổi giây <-> frame_idx (đồng hồ frame_idx ở
        khung xem chi tiết). Đọc bằng TÊN CỘT (csv.DictReader) chứ không theo vị
        trí — thứ tự cột của bộ dữ liệu này KHÁC hệ cũ."""
        cached = self._full_map_cache.get(video)
        if cached is not None:
            return cached
        csv_path = self._maps_csv.get(video)
        rows: list[dict] = []
        if csv_path is not None:
            with open(csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        rows.append({
                            "n": int(row["n"]),
                            "frame_idx": int(row["frame_idx"]),
                            "pts_time": float(row["pts_time"]),
                            "fps": float(row.get("fps") or 0.0),
                        })
                    except (ValueError, KeyError):
                        continue
        rows.sort(key=lambda r: r["n"])
        self._full_map_cache[video] = rows
        return rows

    def full_map(self, video: str) -> list[dict]:
        return self._load_full_map(video)

    def fps(self, video: str) -> float:
        rows = self._load_full_map(video)
        for r in rows:
            if r["fps"] > 0:
                return r["fps"]
        return 25.0     # mặc định an toàn nếu maps CSV thiếu cột fps

    def _load_pts_map(self, video: str) -> dict[int, float]:
        cached = self._pts_cache.get(video)
        if cached is not None:
            return cached
        out = {r["n"]: r["pts_time"] for r in self._load_full_map(video)}
        self._pts_cache[video] = out
        return out

    def pts_time(self, video: str, n: int) -> float | None:
        return self._load_pts_map(video).get(n)

    def video_ns_pts(self, video: str) -> list[tuple[int, float]]:
        """Toàn bộ (n, pts_time) của 1 video, sort theo n — dùng cho asr_align."""
        m = self._load_pts_map(video)
        return sorted(m.items())

    def nearby_ns(self, video: str, n: int, window: int) -> list[int]:
        """Filmstrip: danh sách n lân cận (n-window..n+window) thực sự tồn tại."""
        m = self._load_pts_map(video)
        return sorted(k for k in m if n - window <= k <= n + window)

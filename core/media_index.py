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
import io
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from urllib.parse import quote

import requests

from config import settings

# Giữ kết nối keep-alive tới CDN (bỏ bắt tay TLS mỗi lần tải map).
_http = requests.Session()
_http.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=16))


class MediaIndex:
    def __init__(self):
        self._keyframe_dirs: dict[str, Path] = {}
        self._maps_csv: dict[str, Path] = {}
        self._mp4: dict[str, Path] = {}
        self._pts_cache: dict[str, dict[int, float]] = {}
        self._full_map_cache: dict[str, list[dict]] = {}
        self._remote_map_retry_after: dict[str, float] = {}

    @staticmethod
    def _use_local_keyframes() -> bool:
        return settings.KEYFRAME_SOURCE != "s3"

    @staticmethod
    def _use_cdn_keyframes(video: str) -> bool:
        return (settings.KEYFRAME_SOURCE != "local"
                and bool(settings.KEYFRAME_CDN_BASE_URL)
                and re.fullmatch(r"[A-Za-z0-9_-]+", video) is not None)

    def keyframe_cdn_url(self, video: str, n: int) -> str | None:
        """URL ảnh keyframe trên CDN, hoặc None nếu cấu hình không cho dùng CDN."""
        if n <= 0 or not self._use_cdn_keyframes(video):
            return None
        return f"{settings.KEYFRAME_CDN_BASE_URL}/keyframes/{quote(video, safe='')}/{n:06d}.webp"

    def build(self) -> "MediaIndex":
        if self._use_local_keyframes():
            for d in glob.glob(str(settings.DATA_ROOT / settings.KEYFRAME_GLOB), recursive=True):
                p = Path(d)
                if p.is_dir():
                    self._keyframe_dirs[p.name] = p

            for f in glob.glob(str(settings.DATA_ROOT / settings.MAPS_GLOB), recursive=True):
                p = Path(f)
                self._maps_csv[p.stem] = p
        if settings.KEYFRAME_SOURCE == "s3" and not settings.KEYFRAME_CDN_BASE_URL:
            print("[media_index] cảnh báo: AIC_KEYFRAME_SOURCE=s3 nhưng AIC_KEYFRAME_CDN_BASE_URL "
                  "trống — sẽ không có ảnh keyframe/maps nào.")

        duplicate_videos: dict[str, list[Path]] = {}
        for videos_dir in settings.VIDEO_DIRS:
            if not videos_dir.is_dir():
                print(f"[media_index] bỏ qua thư mục video không tồn tại: {videos_dir}")
                continue
            for f in sorted((*videos_dir.glob("*.mp4"), *videos_dir.glob("*.mov"))):
                existing = self._mp4.get(f.stem)
                if existing is None:
                    self._mp4[f.stem] = f
                else:
                    duplicate_videos.setdefault(f.stem, [existing]).append(f)

        if duplicate_videos:
            examples = ", ".join(
                f"{video} ({' | '.join(map(str, paths))})"
                for video, paths in list(duplicate_videos.items())[:5]
            )
            print(
                f"[media_index] cảnh báo: {len(duplicate_videos)} video trùng tên; "
                f"ưu tiên thư mục xuất hiện trước. Ví dụ: {examples}"
            )

        print(f"[media_index] nguồn keyframe={settings.KEYFRAME_SOURCE}, "
              f"{len(self._keyframe_dirs):,} thư mục keyframe, "
              f"{len(self._maps_csv):,} maps CSV, {len(self._mp4):,} video mp4/mov "
              f"từ {len(settings.VIDEO_DIRS)} thư mục cấu hình")
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
        if not self._use_local_keyframes():
            return None
        p = settings.DATA_ROOT / "thumbs_320" / video / f"{n:06d}.webp"
        if p.exists():
            return p
        return self.resolve_frame_path(video, n)

    def resolve_video_path(self, video: str) -> Path | None:
        return self._mp4.get(video)

    def _fetch_remote_map(self, video: str) -> str | None:
        """Maps CSV từ CDN, qua cache đĩa (map không đổi). ĐÃ ĐO: mỗi lần tải lạnh
        ~250ms, trước đây tải TUẦN TỰ cho từng video Batch 2 trong kết quả -> một
        truy vấn có ~50 video Batch 2 mất thêm vài giây."""
        cache_file = settings.CDN_MAPS_CACHE_DIR / f"{video}.csv"
        try:
            return cache_file.read_text(encoding="utf-8")
        except OSError:
            pass
        url = f"{settings.KEYFRAME_CDN_BASE_URL}/maps/{quote(video, safe='')}.csv"
        try:
            response = _http.get(url, timeout=3)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_file.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_text(response.text, encoding="utf-8")
            tmp.replace(cache_file)
        except OSError:
            pass    # cache chỉ là tăng tốc, lỗi ghi không được làm hỏng truy vấn
        return response.text

    def prefetch_maps(self, videos) -> None:
        """Nạp SONG SONG maps của các video chưa có trong RAM — gọi trước khi
        dựng kết quả để pts_time() không phải tải từng video một."""
        missing = [v for v in dict.fromkeys(videos)
                   if v not in self._full_map_cache and v not in self._maps_csv
                   and self._use_cdn_keyframes(v)]
        if not missing:
            return
        with ThreadPoolExecutor(max_workers=min(16, len(missing))) as pool:
            list(pool.map(self._load_full_map, missing))

    def warm_remote_maps_async(self, videos) -> None:
        """Nạp nền maps CDN của mọi video lúc khởi động (lần đầu tải về cache đĩa,
        các lần sau chỉ đọc đĩa)."""
        videos = list(videos)
        if not videos or settings.KEYFRAME_SOURCE == "local" or not settings.KEYFRAME_CDN_BASE_URL:
            return

        def _run():
            t0 = monotonic()
            self.prefetch_maps(videos)
            print(f"[media_index] đã nạp nền maps CDN cho {len(videos):,} video "
                  f"({monotonic() - t0:.0f}s)")
        threading.Thread(target=_run, name="warm-remote-maps", daemon=True).start()

    def _load_full_map(self, video: str) -> list[dict]:
        """Bảng map ĐẦY ĐỦ của 1 video: [{n, frame_idx, pts_time, fps}] sort theo n.
        Đây là NGUỒN CHÂN LÝ để quy đổi giây <-> frame_idx (đồng hồ frame_idx ở
        khung xem chi tiết). Đọc bằng TÊN CỘT (csv.DictReader) chứ không theo vị
        trí — thứ tự cột của bộ dữ liệu này KHÁC hệ cũ.

        +1 NGAY TẠI ĐÂY (nguồn đọc CSV): CSV lưu chỉ số 0-based từ decord (khung
        ĐẦU TIÊN của video = 0, quy ước lập trình thông thường). BTC xác nhận
        trực tiếp: khung ĐẦU TIÊN của video tính là frame 1 (không phải 0) —
        đúng theo cách Media Player Classic (công cụ BTC gợi ý để tự kiểm tra
        frame_idx, Ctrl+G/Navigate→Go To) đếm khung. +1 ở NGUỒN đọc CSV (nơi
        DUY NHẤT đọc trực tiếp cột frame_idx thô) để MỌI nơi dùng dữ liệu này
        (đồng hồ frame_idx lúc tua video, /videos/*/map, /videos/*/keyframes)
        tự động nhất quán, không phải nhớ +1 rải rác ở từng chỗ dùng."""
        cached = self._full_map_cache.get(video)
        if cached is not None:
            return cached
        csv_path = self._maps_csv.get(video)
        rows: list[dict] = []
        source = None
        if csv_path is not None:
            source = open(csv_path, newline="", encoding="utf-8")
        elif (self._use_cdn_keyframes(video)
              and monotonic() >= self._remote_map_retry_after.get(video, 0.0)):
            text = self._fetch_remote_map(video)
            if text is not None:
                source = io.StringIO(text)
            else:
                self._remote_map_retry_after[video] = monotonic() + 60
        if source is not None:
            with source:
                for row in csv.DictReader(source):
                    try:
                        rows.append({
                            "n": int(row["n"]),
                            "frame_idx": int(row["frame_idx"]) + 1,
                            "pts_time": float(row["pts_time"]),
                            "fps": float(row.get("fps") or 0.0),
                        })
                    except (ValueError, KeyError):
                        continue
        rows.sort(key=lambda r: r["n"])
        if rows:
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
        if out:
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

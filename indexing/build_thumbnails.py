"""Tien sinh thumbnail 320px cho toan bo keyframe (167,850 anh) — GIAI DOAN 1
cua thiet ke UI/UX moi (PHAN I.4 muc 1, "Thap thumbnail"). Luoi ket qua dung
ban 320px (nhe, tai nhanh); khung xem chi tiet dung ban goc (dinh chinh trong
media_index/media.py, khong doi).

Chay 1 LAN, offline, khong can Docker/backend dang chay — chi doc/ghi truc
tiep tren dia. Idempotent: bo qua file da co (resume duoc neu bi ngat giua
chung).

Output: aic-system/data/thumbs_320/<video>/<n:06d>.webp — cung layout phang
voi thu muc goc, khac voi 2 kieu thu muc nguon (raw_*/**/keyframes/*), de
media_index.resolve_thumb_path() tra don gian (video -> 1 thu muc duy nhat).

Chay: python aic-system/indexing/build_thumbnails.py
"""
from __future__ import annotations

import glob
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings  # noqa: E402

THUMB_SIZE = (320, 180)   # 16:9, khop ty le keyframe that
THUMB_ROOT = settings.DATA_ROOT / "thumbs_320"
QUALITY = 80


def main():
    THUMB_ROOT.mkdir(parents=True, exist_ok=True)

    keyframe_dirs: dict[str, Path] = {}
    for d in glob.glob(str(settings.DATA_ROOT / settings.KEYFRAME_GLOB), recursive=True):
        p = Path(d)
        if p.is_dir():
            keyframe_dirs[p.name] = p
    print(f">>> {len(keyframe_dirs):,} video co thu muc keyframe nguon", flush=True)

    t0 = time.time()
    n_done = 0
    n_skip = 0
    n_err = 0
    n_total_videos = len(keyframe_dirs)

    for vi, (video, src_dir) in enumerate(sorted(keyframe_dirs.items()), 1):
        dst_dir = THUMB_ROOT / video
        dst_dir.mkdir(parents=True, exist_ok=True)
        for src_path in sorted(src_dir.glob("*.webp")):
            dst_path = dst_dir / src_path.name
            if dst_path.exists():
                n_skip += 1
                continue
            try:
                with Image.open(src_path) as im:
                    im = im.convert("RGB")
                    im.thumbnail(THUMB_SIZE, Image.LANCZOS)
                    im.save(dst_path, "WEBP", quality=QUALITY)
                n_done += 1
            except Exception as e:
                n_err += 1
                print(f"  !! loi {src_path}: {e}", flush=True)

        if vi % 20 == 0 or vi == n_total_videos:
            elapsed = time.time() - t0
            rate = n_done / elapsed if elapsed > 0 else 0
            print(f"  [{vi}/{n_total_videos} video] done={n_done:,} skip={n_skip:,} "
                  f"err={n_err} | {elapsed/60:.1f} phut | {rate:.0f} anh/s", flush=True)

    print(f"\n>>> XONG: {n_done:,} thumbnail moi, {n_skip:,} da co san, "
          f"{n_err} loi, {(time.time()-t0)/60:.1f} phut", flush=True)


if __name__ == "__main__":
    main()

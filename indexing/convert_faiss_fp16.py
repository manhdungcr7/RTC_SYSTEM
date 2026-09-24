"""Chuyển các nhánh FAISS `IndexFlatIP` (float32) sang `IndexScalarQuantizer`
fp16 — giảm một nửa dung lượng để TOÀN BỘ index nằm vừa trong RAM.

VÌ SAO: 6 nhánh float32 = ~6,6GB. Trong Docker Desktop (WSL2, ~7,6GB RAM) chúng
không vừa page cache, bị đẩy ra rồi đọc lại qua bind-mount Windows (9p, đo thật
~109MB/s) -> truy vấn đầu tiên sau một lúc nghỉ mất 10-60 giây. Bản fp16 ~3,3GB
nạp thẳng vào RAM một lần lúc khởi động (xem FaissRepo, AIC_FAISS_LOAD).

KHÔNG MẤT CHÍNH XÁC so với nguồn: embedding gốc (feat_*.npy) vốn đã là float16;
float32 trong IndexFlatIP chỉ là bản nới rộng của cùng giá trị đó.

Ghi ra thư mục riêng, KHÔNG sửa index đang chạy. Sau khi chạy xong và kiểm tra:
dừng backend, đổi tên thư mục (xem --help / HANDOVER), khởi động lại.

    python indexing/convert_faiss_fp16.py --src docker/volumes/faiss --out docker/volumes/faiss_fp16
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

import faiss
import numpy as np

CHUNK = 65536


def convert(src_dir: Path, out_dir: Path) -> None:
    src = faiss.read_index(str(src_dir / "index.faiss"))
    if isinstance(src, faiss.IndexScalarQuantizer):
        print(f"  {src_dir.name}: đã là ScalarQuantizer -> chép nguyên")
        out_dir.mkdir(parents=True)
        shutil.copy2(src_dir / "index.faiss", out_dir / "index.faiss")
        shutil.copy2(src_dir / "meta.parquet", out_dir / "meta.parquet")
        return
    if not isinstance(src, faiss.IndexFlat) or src.metric_type != faiss.METRIC_INNER_PRODUCT:
        raise TypeError(f"{src_dir.name}: chỉ hỗ trợ IndexFlatIP, gặp {type(src).__name__}")

    t0 = time.time()
    dst = faiss.IndexScalarQuantizer(src.d, faiss.ScalarQuantizer.QT_fp16, faiss.METRIC_INNER_PRODUCT)
    for start in range(0, src.ntotal, CHUNK):
        n = min(CHUNK, src.ntotal - start)
        dst.add(src.reconstruct_n(start, n))
    if dst.ntotal != src.ntotal:
        raise RuntimeError(f"{src_dir.name}: lệch số dòng {dst.ntotal} != {src.ntotal}")

    # Kiểm tra: top-100 của fp16 phải trùng top-100 của float32 với truy vấn thật
    # (vector có sẵn trong index), không chỉ vector ngẫu nhiên.
    rng = np.random.default_rng(0)
    probe = np.stack([src.reconstruct(int(i)) for i in rng.choice(src.ntotal, 20, replace=False)])
    _, a = src.search(probe, 100)
    _, b = dst.search(probe, 100)
    overlap = np.mean([len(set(x) & set(y)) / 100 for x, y in zip(a, b)])
    if overlap < 0.98:
        raise RuntimeError(f"{src_dir.name}: top-100 fp16 chỉ trùng {overlap:.1%} so với float32")

    out_dir.mkdir(parents=True)
    faiss.write_index(dst, str(out_dir / "index.faiss"))
    shutil.copy2(src_dir / "meta.parquet", out_dir / "meta.parquet")
    size = (out_dir / "index.faiss").stat().st_size / 1e9
    print(f"  {src_dir.name}: {dst.ntotal:,} vector, {size:.2f}GB, top-100 trùng {overlap:.1%}, "
          f"{time.time() - t0:.0f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--branches", nargs="*", help="mặc định: mọi nhánh có index.faiss (bỏ *_backup*)")
    args = ap.parse_args()

    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit(f"Thư mục đích không rỗng: {args.out}")
    branches = args.branches or sorted(
        d.name for d in args.src.iterdir()
        if (d / "index.faiss").exists() and "backup" not in d.name)
    print(f"Chuyển {branches} -> {args.out}")
    for b in branches:
        convert(args.src / b, args.out / b)
    print("XONG.")


if __name__ == "__main__":
    main()

"""
================================================================================
KAGGLE NOTEBOOK — GỘP nhiều dataset keyframe (từ notebook 01) thành 1 dataset duy nhất
================================================================================
Dùng khi đã có nhiều dataset keyframe rời rạc (VD aic-kf-l21a, aic-kf-account0..4 —
16 shard batch 1) và muốn gộp lại còn 1 dataset để Add Input cho tiện (thay vì add
6 cái mỗi lần chạy notebook 02/03/04).

CẤU HÌNH KAGGLE:
  - Accelerator : KHÔNG CẦN GPU (chỉ copy file — chọn "None" để khỏi tốn quota GPU)
  - Internet    : KHÔNG CẦN (chỉ đọc Input đã có sẵn, không tải gì thêm)
  - Add Input   : add TẤT CẢ dataset keyframe muốn gộp (VD aic-kf-l21a, aic-kf-account0,
                  aic-kf-account1, aic-kf-account2, aic-kf-account3, aic-kf-account4)

Xử lý 2 kiểu cấu trúc dataset (tự nhận diện):
  - Kiểu CŨ (aic-kf-l21a, tạo trước khi notebook 01 hỗ trợ nhiều shard/lần chạy):
      out/keyframes/<video>/*.webp, out/maps/<video>.csv, out/audio/<video>.opus,
      out/shard_<SHARD>_info.json  (đọc field "shard" trong file này để biết tên shard)
  - Kiểu MỚI (aic-kf-account0..4, nhiều shard/lần chạy):
      out/<shard>/keyframes/..., out/<shard>/maps/..., out/<shard>/audio/...

ĐẦU RA: /kaggle/working/out/<shard>/{keyframes,maps,audio}/...  — CÙNG 1 CẤU TRÚC cho
mọi shard, sẵn sàng Save Version -> New Dataset (VD tên "aic-kf-batch1-all").
================================================================================
"""
import json
import shutil
from pathlib import Path

VERSION = "merge-keyframe-datasets v1"
print(f">>> {VERSION}", flush=True)

INPUT_ROOT = Path("/kaggle/input")
OUT = Path("/kaggle/working/out")
OUT.mkdir(parents=True, exist_ok=True)

merged_shards = set()
skipped = []

# Kaggle có thể mount dataset ở /kaggle/input/<ten-dataset>/... HOẶC lồng thêm cấp
# /kaggle/input/datasets/<username>/<ten-dataset>/... (tuỳ phiên bản/loại tài khoản) —
# KHÔNG giả định số cấp lồng, quét rglob toàn bộ để tìm MỌI thư mục "out" (= mỗi cái
# là 1 dataset đã add).
out_dirs = sorted({p for p in INPUT_ROOT.rglob("out") if p.is_dir()})
print(f"  Tim thay {len(out_dirs)} thu muc 'out' (= {len(out_dirs)} dataset da add):", flush=True)
for p in out_dirs:
    print(f"    - {p}", flush=True)

for src_out in out_dirs:
    ds_name = src_out.parent.name  # tên dataset (thư mục cha của "out")

    sub = {p.name for p in src_out.iterdir() if p.is_dir()}

    if {"keyframes", "maps", "audio"}.issubset(sub):
        # ---- kieu CU: 1 dataset = 1 shard, khong long ten shard ----
        info_files = list(src_out.glob("shard_*_info.json"))
        if info_files:
            shard = json.load(open(info_files[0])).get("shard")
        else:
            shard = ds_name.replace("aic-kf-", "")
        if not shard:
            print(f"  [BO QUA] {ds_name}: khong xac dinh duoc ten shard", flush=True)
            skipped.append(ds_name)
            continue
        dst = OUT / shard
        dst.mkdir(parents=True, exist_ok=True)
        for kind in ["keyframes", "maps", "audio"]:
            s, d = src_out / kind, dst / kind
            if s.exists():
                shutil.copytree(s, d, dirs_exist_ok=True)
        merged_shards.add(shard)
        print(f"  [OK] {ds_name} -> shard '{shard}' (kieu cu)", flush=True)
    else:
        # ---- kieu MOI: 1 dataset = nhieu shard, da long ten shard san ----
        n_before = len(merged_shards)
        for shard_dir in src_out.iterdir():
            if not shard_dir.is_dir():
                continue
            shard = shard_dir.name
            dst = OUT / shard
            dst.mkdir(parents=True, exist_ok=True)
            for kind in ["keyframes", "maps", "audio"]:
                s, d = shard_dir / kind, dst / kind
                if s.exists():
                    shutil.copytree(s, d, dirs_exist_ok=True)
            merged_shards.add(shard)
        print(f"  [OK] {ds_name} -> {len(merged_shards)-n_before} shard (kieu moi): "
              f"{sorted([p.name for p in src_out.iterdir() if p.is_dir()])}", flush=True)

# ==================== TỔNG KẾT ====================
total_kf = sum(1 for _ in OUT.rglob("*.webp"))
total_videos = sum(len(list((OUT / s / "keyframes").iterdir())) for s in merged_shards if (OUT / s / "keyframes").exists())
print("\n" + "=" * 60, flush=True)
print(f"  Da gop {len(merged_shards)} shard: {sorted(merged_shards)}", flush=True)
print(f"  Tong video: {total_videos} | Tong keyframe: {total_kf:,}", flush=True)
if skipped:
    print(f"  Dataset BI BO QUA (kiem tra lai): {skipped}", flush=True)
print("=" * 60, flush=True)

# ==================== NÉN THÀNH .tar (QUAN TRỌNG) ====================
# Kaggle commit/snapshot Output theo TỪNG FILE — 180k+ file webp rời rạc làm bước
# "Save Version" TREO HÀNG GIỜ (đã gặp thật). Nén thành vài file .tar lớn (1 file/shard)
# để Kaggle chỉ cần xử lý 16 file thay vì 182,422 file — nhanh hơn RẤT nhiều.
import tarfile
ARCHIVE_DIR = Path("/kaggle/working/archives")
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
print("\n" + "=" * 60, "\n  NEN THANH .tar (de Kaggle commit nhanh)\n", "=" * 60, flush=True)
for shard in sorted(merged_shards):
    tar_path = ARCHIVE_DIR / f"{shard}.tar"
    with tarfile.open(tar_path, "w") as tar:
        tar.add(OUT / shard, arcname=shard)
    print(f"  [TAR] {shard}.tar ({tar_path.stat().st_size/1e6:.0f} MB)", flush=True)

# xoá cây file rời sau khi đã nén — KHÔNG để Kaggle commit cả 2 bản (rời + nén)
shutil.rmtree(OUT)
print(f"\n  Da xoa cay file roi trong 'out/' — CHI GIU archives/*.tar de commit.", flush=True)

print("\n>>> XONG. Save Version -> tab Output -> New Dataset (VD ten 'aic-kf-batch1-all').", flush=True)
print(">>> Output gio la 16 file archives/<shard>.tar — notebook 02/03/04 se tu giai nen khi doc.", flush=True)

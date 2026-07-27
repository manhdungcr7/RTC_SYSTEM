"""
================================================================================
KAGGLE NOTEBOOK 04 — ENCODE EMBEDDING (DINOv3, công cụ "tìm ảnh giống") từ keyframe
================================================================================
Chạy độc lập với 02/03. KHÔNG cần video — chỉ cần keyframe dataset (nhẹ) → nhanh.
DINOv3 KHÔNG vào ensemble text→image (không có text-encoder) — dùng riêng cho tính
năng "upload 1 ảnh mẫu, tìm ảnh giống trong index" (image→image, cosine similarity
trên chính embedding này).

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (hoặc P100)
  - Internet    : ON (tải model từ HuggingFace lần đầu)
  - Add Input   : (các) dataset keyframe từ notebook 01

ĐẦU RA (/kaggle/working/emb_dinov3 → Save Version → Kaggle Dataset "aic-feat-dinov3-<shard>"):
  feat_dinov3.npy       (N, D) float16 — vector ẢNH, ĐÃ L2-normalize
  feat_index.parquet    N dòng: video, n, frame_idx — song song từng vector (để join)
  emb_info.json
================================================================================
"""
import os, sys, json, time, glob
from pathlib import Path
import numpy as np

VERSION = "04-embed-dinov3 v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_ID = os.environ.get("MODEL_ID", "facebook/dinov3-vitl16-pretrain-lvd1689m")
TAG      = os.environ.get("TAG", "dinov3")
BATCH    = int(os.environ.get("BATCH", "64"))
KF_ROOT_GLOB  = "/kaggle/input/**/keyframes"
MAP_ROOT_GLOB = "/kaggle/input/**/maps"

WORK = Path("/kaggle/working"); OUT = WORK / "emb_dinov3"; OUT.mkdir(parents=True, exist_ok=True)

# Nếu dataset input là bản GỘP (tạo bởi merge_keyframe_datasets.py, chứa archives/<shard>.tar
# thay vì cây file rời — để Kaggle commit nhanh) → tự giải nén vào /kaggle/working trước.
_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
if _tar_files:
    import tarfile
    LOCAL_KF = WORK / "kf_extracted"; LOCAL_KF.mkdir(parents=True, exist_ok=True)
    print(f"  Phat hien {len(_tar_files)} file .tar (dataset gop) — giai nen truoc...", flush=True)
    for tf in _tar_files:
        with tarfile.open(tf) as t:
            t.extractall(LOCAL_KF)
    KF_ROOT_GLOB = f"{LOCAL_KF}/**/keyframes"
    MAP_ROOT_GLOB = f"{LOCAL_KF}/**/maps"

import subprocess
subprocess.run(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' pyarrow pandas", shell=True)
subprocess.run(f"{sys.executable} -m pip install -q 'pillow==11.1.0'", shell=True)  # ghim bản ổn định (xem 02_embed.py)

import torch
from PIL import Image
import transformers
print(f"  transformers = {transformers.__version__}", flush=True)

# DINOv3 la model "gated" (can duoc Meta duyet + xac thuc bang token khi tai, du
# da duoc duyet quyen). Doc token tu Kaggle Secrets (Add-ons > Secrets, dat ten
# "HF_TOKEN") hoac bien moi truong HF_TOKEN neu co.
_hf_token = None
try:
    from kaggle_secrets import UserSecretsClient
    _hf_token = UserSecretsClient().get_secret("HF_TOKEN")
except Exception:
    _hf_token = os.environ.get("HF_TOKEN")
if _hf_token:
    from huggingface_hub import login
    login(token=_hf_token)
    print("  Da dang nhap HuggingFace bang HF_TOKEN.", flush=True)
else:
    print("  [CANH BAO] KHONG tim thay HF_TOKEN — model DINOv3 (gated) se loi 403 "
          "khi tai. Xem huong dan them Secret trong README_KAGGLE.md.", flush=True)

from transformers import AutoModel, AutoImageProcessor
dev = "cuda" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev=='cuda' else 'KHONG CO GPU!'}", flush=True)

proc = AutoImageProcessor.from_pretrained(MODEL_ID)
# QUAN TRONG: fp16 THUAN gay NaN 100% tren T4 (da xac nhan that — T4/Turing khong ho
# tro bf16, chi co fp16, va DINOv3 bi tran so/overflow khi chay fp16 thuan). Dung fp32
# cho model nay (cham hon ~1.3-2x nhung an toan tuyet doi, khong co lua chon bf16 tren T4).
model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=torch.float32).to(dev).eval()
print(f"  --> {MODEL_ID} san sang (fp32 — tranh NaN da gap tren T4 voi fp16)", flush=True)


@torch.no_grad()
def encode_images(pil_list):
    inp = proc(images=pil_list, return_tensors="pt").to(dev)
    out = model(**inp)
    # DINOv3: dùng pooler_output nếu có, không thì mean-pool patch tokens (bỏ CLS)
    feat = getattr(out, "pooler_output", None)
    if feat is None:
        feat = out.last_hidden_state[:, 1:, :].mean(dim=1)
    feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    return feat.float().cpu().numpy().astype(np.float16)


# ==================== GOM DANH SÁCH KEYFRAME (theo maps CSV) ====================
print("=" * 60, "\n[2/3] Gom danh sach keyframe\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
map_roots = glob.glob(MAP_ROOT_GLOB, recursive=True)
if not kf_roots:
    raise FileNotFoundError("Khong thay thu muc 'keyframes' trong /kaggle/input — nho Add dataset tu notebook 01.")
print(f"  keyframes roots: {kf_roots}", flush=True)

items = []
for mroot in map_roots:
    for csv in sorted(glob.glob(os.path.join(mroot, "*.csv"))):
        video = Path(csv).stem
        img_dir = None
        for kr in kf_roots:
            d = os.path.join(kr, video)
            if os.path.isdir(d):
                img_dir = d; break
        if img_dir is None:
            continue
        with open(csv) as f:
            next(f)
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                n, frame_idx = int(parts[0]), int(parts[1])
                p = os.path.join(img_dir, f"{n:06d}.webp")
                if os.path.exists(p):
                    items.append((video, n, frame_idx, p))
print(f"  --> {len(items):,} keyframe se encode", flush=True)
if not items:
    raise RuntimeError("0 keyframe khop giua maps/ va keyframes/ — kiem tra dataset input.")


# ==================== ENCODE ====================
print("=" * 60, "\n[3/3] Encode embedding\n", "=" * 60, flush=True)
out = None
t0 = time.time()
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    imgs = []
    for (_, _, _, p) in chunk:
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception:
            imgs.append(Image.new("RGB", (384, 384)))
    v = encode_images(imgs)
    if not np.isfinite(v).all():
        raise RuntimeError(
            f"NaN/Inf o batch {bi} — kiem tra lai dtype model (da tung gap NaN 100% "
            f"voi fp16 tren T4, xem comment o tren). DUNG luon, khong luu file hong.")
    if out is None:
        out = np.zeros((len(items), v.shape[1]), dtype=np.float16)
    out[bi:bi + len(v)] = v
    if (bi // BATCH) % 20 == 0:
        done = bi + len(v)
        r = done / (time.time() - t0)
        print(f"  {done:,}/{len(items):,} | {r:.1f} img/s | con ~{(len(items)-done)/max(r,1e-6)/60:.1f} phut", flush=True)

np.save(OUT / f"feat_{TAG}.npy", out)

import pandas as pd
df = pd.DataFrame([(v, n, fi) for (v, n, fi, _) in items], columns=["video", "n", "frame_idx"])
df.to_parquet(OUT / "feat_index.parquet")
info = {"model": MODEL_ID, "tag": TAG, "n": len(items), "dim": int(out.shape[1]),
        "dtype": "float16", "minutes": round((time.time() - t0) / 60, 1)}
json.dump(info, open(OUT / "emb_info.json", "w"), indent=2)
mb = (OUT / f"feat_{TAG}.npy").stat().st_size / 1e6
print(f"  feat_{TAG}.npy: {out.shape} ({mb:.0f} MB) | {info['minutes']} phut", flush=True)
print("\n>>> XONG. Save Version -> tao Dataset 'aic-feat-dinov3-<shard>'.", flush=True)

"""
================================================================================
KAGGLE NOTEBOOK 05 — ENCODE EMBEDDING (BEiT-3, dự phòng ensemble) từ keyframe
================================================================================
Chạy độc lập với 02/03/04. KHÔNG cần video — chỉ cần keyframe dataset (nhẹ) → nhanh.
BEiT-3 KHÔNG còn là nhánh chi tiết mặc định (đã thay bằng PE-Core — xem
NGHIEN_CUU_KIEN_TRUC.md mục 9.7) nhưng vẫn trích ẢNH song song ở đây (offline, free
trên Kaggle) để giữ tuỳ chọn ensemble sau này nếu đo trên GT thấy có lợi thật (đợt
trước BEiT-3 từng +27% QA khi đi cùng MetaCLIP-2). KHÔNG nạp online cùng PE-Core
(3.44GB + 2.3GB > 4GB VRAM laptop, xem 9.7).

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (hoặc P100)
  - Internet    : ON (git clone unilm + tải checkpoint)
  - Add Input   : (các) dataset keyframe từ notebook 01 (VD aic-kf-batch1-all)

Cài đặt: đúng công thức đã CHỨNG MINH chạy được trên Kaggle trước đây
(system/kaggle/aic_beit3_query.py — dùng để encode text GT, giờ dùng lại đúng cách
cài đặt cho encode ẢNH) — git clone unilm (KHÔNG tự chép rời file, tránh thiếu phụ
thuộc), timm==0.4.12 (bản cũ, khớp checkpoint), torchscale, torchmetrics, tensorboardX.

ĐẦU RA (/kaggle/working/emb_beit3 → Save Version → Kaggle Dataset "aic-feat-beit3-<shard>"):
  feat_beit3.npy        (N, 1024) float16 — vector ẢNH (vision_cls), ĐÃ L2-normalize
  feat_index.parquet    N dòng: video, n, frame_idx — song song từng vector (để join)
  emb_info.json
================================================================================
"""
import os, sys, json, time, glob, subprocess, collections.abc as _abc, types as _types
from pathlib import Path
import numpy as np

VERSION = "05-embed-beit3 v1"
print(f">>> {VERSION}", flush=True)

# --- VÁ torch._six (giống aic_beit3_query.py / beit3_server đã dùng, torch mới đã xoá module này) ---
_six = _types.ModuleType("torch._six")
_six.container_abcs = _abc; _six.string_classes = (str, bytes)
_six.int_classes = (int,); _six.inf = float("inf"); _six.nan = float("nan")
sys.modules["torch._six"] = _six

# ============================ CẤU HÌNH ============================
TAG   = os.environ.get("TAG", "beit3")
BATCH = int(os.environ.get("BATCH", "32"))
KF_ROOT_GLOB  = "/kaggle/input/**/keyframes"
MAP_ROOT_GLOB = "/kaggle/input/**/maps"

WORK = Path("/kaggle/working"); OUT = WORK / "emb_beit3"; OUT.mkdir(parents=True, exist_ok=True)

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


def sh(c, check=False):
    print("$", c, flush=True)
    r = subprocess.run(c, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(c)
    return r


# ==================== 1. CÀI ĐẶT (đúng công thức đã chạy được trên Kaggle) ====================
print("=" * 60, "\n[1/4] Cai dat + tai model BEiT-3\n", "=" * 60, flush=True)
sh("git clone --depth 1 https://github.com/microsoft/unilm.git /kaggle/temp/unilm", check=True)
sh(f"{sys.executable} -m pip install -q timm==0.4.12 torchscale==0.2.0 sentencepiece "
   f"ftfy torchmetrics tensorboardX pyarrow pandas pillow 2>/dev/null")

REL = "https://github.com/addf400/files/releases/download/beit3"
sh(f'wget -q -O /kaggle/temp/beit3_large_patch16_384_coco_retrieval.pth "{REL}/beit3_large_patch16_384_coco_retrieval.pth"')
assert Path("/kaggle/temp/beit3_large_patch16_384_coco_retrieval.pth").stat().st_size > 1_000_000_000, \
    "Tai checkpoint BEiT-3 that bai — kiem tra Internet ON"

sys.path.append("/kaggle/temp/unilm/beit3")
import torch
from PIL import Image
import torchvision.transforms as T
from timm.data.constants import IMAGENET_INCEPTION_MEAN, IMAGENET_INCEPTION_STD
import modeling_finetune  # noqa: E402  (đăng ký kiến trúc @register_model)
from modeling_finetune import beit3_large_patch16_384_retrieval

dev = "cuda" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev=='cuda' else 'KHONG CO GPU!'}", flush=True)

model = beit3_large_patch16_384_retrieval(pretrained=False)
ck = torch.load("/kaggle/temp/beit3_large_patch16_384_coco_retrieval.pth", map_location="cpu")
model.load_state_dict(ck.get("model", ck))
model = model.to(dev).eval()
print("  --> model san sang", flush=True)

# transform CHUẨN retrieval-eval của BEiT-3 (build_transform, nhánh is_train=False, task != imagenet)
# — Resize thẳng 384x384 (bicubic) + Normalize IMAGENET_INCEPTION — khớp lúc train checkpoint này.
preprocess = T.Compose([
    T.Resize((384, 384), interpolation=T.InterpolationMode.BICUBIC),
    T.ToTensor(),
    T.Normalize(mean=IMAGENET_INCEPTION_MEAN, std=IMAGENET_INCEPTION_STD),
])


@torch.no_grad()
def encode_images(pil_list):
    batch = torch.stack([preprocess(im) for im in pil_list]).to(dev)
    vision_cls, _ = model(image=batch, only_infer=True)
    vision_cls = torch.nn.functional.normalize(vision_cls, dim=-1)
    return vision_cls.float().cpu().numpy().astype(np.float16)


# ==================== 2. GOM DANH SÁCH KEYFRAME (theo maps CSV) ====================
print("=" * 60, "\n[2/4] Gom danh sach keyframe\n", "=" * 60, flush=True)
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


# ==================== 3. ENCODE ====================
print("=" * 60, "\n[3/4] Encode embedding\n", "=" * 60, flush=True)
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
    if out is None:
        out = np.zeros((len(items), v.shape[1]), dtype=np.float16)
    out[bi:bi + len(v)] = v
    if (bi // BATCH) % 20 == 0:
        done = bi + len(v)
        r = done / (time.time() - t0)
        print(f"  {done:,}/{len(items):,} | {r:.1f} img/s | con ~{(len(items)-done)/max(r,1e-6)/60:.1f} phut", flush=True)

np.save(OUT / f"feat_{TAG}.npy", out)

# ==================== 4. LƯU INDEX SONG SONG + INFO ====================
print("=" * 60, "\n[4/4] Luu index + info\n", "=" * 60, flush=True)
import pandas as pd
df = pd.DataFrame([(v, n, fi) for (v, n, fi, _) in items], columns=["video", "n", "frame_idx"])
df.to_parquet(OUT / "feat_index.parquet")
info = {"model": "beit3_large_patch16_384_coco_retrieval", "tag": TAG, "n": len(items), "dim": int(out.shape[1]),
        "dtype": "float16", "minutes": round((time.time() - t0) / 60, 1)}
json.dump(info, open(OUT / "emb_info.json", "w"), indent=2)
mb = (OUT / f"feat_{TAG}.npy").stat().st_size / 1e6
print(f"  feat_{TAG}.npy: {out.shape} ({mb:.0f} MB) | {info['minutes']} phut", flush=True)
print("\n>>> XONG. Save Version -> tao Dataset 'aic-feat-beit3-<shard>'.", flush=True)
print(">>> feat_index.parquet giu (video,n,frame_idx) song song tung vector — dung de join khi search.", flush=True)

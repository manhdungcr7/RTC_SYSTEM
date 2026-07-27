"""
================================================================================
KAGGLE NOTEBOOK 03 — ENCODE EMBEDDING (PE-Core-L14-336, nhánh CHI TIẾT) từ keyframe
================================================================================
Chạy SAU notebook 01 (và độc lập với 02 — không cần chạy 02 trước). KHÔNG cần video
— chỉ cần keyframe dataset (nhẹ) → nhanh. Đây là nhánh "chi tiết" đã CHỐT thay cho
BEiT-3/LLM2CLIP (xem NGHIEN_CUU_KIEN_TRUC.md mục 9.7/9.7b — PE-Core thắng cả 3 mặt:
nhanh hơn, nhẹ VRAM hơn, điểm cao hơn khi test thật; dùng bản L thay G vì retrieval
gần ngang nhau nhưng G quá chậm trên T4 — đo thật 3.5 ảnh/s ≈ 13-15 giờ, L ~21 ảnh/s).

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (hoặc P100)
  - Internet    : ON  (tải mã nguồn core/vision_encoder từ GitHub + checkpoint từ HF)
  - Add Input   : dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all)

Model: facebook/PE-Core-L14-336 (Perception Encoder, Meta, arXiv 2504.13181) —
checkpoint ~2.7GB. KHÔNG cần cài xformers/torchcodec (đã đọc source xác nhận encode
ảnh không phụ thuộc 2 gói đó — chỉ cần torch/torchvision/timm/einops).

CHIA CHO NHIỀU ACCOUNT CHẠY SONG SONG (tuỳ chọn, để nhanh hơn nữa):
  đặt biến môi trường SHARDS="L21_a,L22_a,L23_a" để account đó CHỈ xử lý các shard
  trong danh sách (các account khác chạy CÙNG script này với SHARDS khác nhau, không
  trùng nhau). Để trống (mặc định) = xử lý HẾT 16 shard trong 1 account.
  VD chia 2 account (16 shard ÷ 2 ≈ 8 shard/account):
    Account A: SHARDS="L21_a,L22_a,L23_a,L24_a,L25_a,L25_a1,L25_b,L26_a"
    Account B: SHARDS="L26_b,L26_c,L26_d,L26_e,L27_a,L28_a,L29_a,L30_a"

ĐẦU RA (/kaggle/working/emb_pecore → Save Version → Kaggle Dataset "aic-feat-pecore-<shard>"):
  feat_pecore.npy       (N, D) float16 — vector ẢNH, ĐÃ L2-normalize (D=1024 cho L scale)
  feat_index.parquet    N dòng: video, n, frame_idx  — song song từng vector (để join)
  emb_info.json
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path
import numpy as np

VERSION = "03-embed-pecore v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_NAME = os.environ.get("MODEL_NAME", "PE-Core-L14-336")  # doi tu G sang L: retrieval gan bang
                                                                # nhau (Flickr30K R@1 91.05 vs 90.95,
                                                                # xem NGHIEN_CUU_KIEN_TRUC.md 9.7) nhung
                                                                # nhe hon ~6 lan → T4 chay kip (G qua cham,
                                                                # do thuc te: 3.5 anh/s ≈ 13-15 gio/batch1)
TAG        = os.environ.get("TAG", "pecore")
BATCH      = int(os.environ.get("BATCH", "48"))
KF_ROOT_GLOB  = "/kaggle/input/**/keyframes"
MAP_ROOT_GLOB = "/kaggle/input/**/maps"

WORK = Path("/kaggle/working"); OUT = WORK / "emb_pecore"; OUT.mkdir(parents=True, exist_ok=True)
PE_SRC = Path("/kaggle/working/pe_src")
PE_SRC.mkdir(parents=True, exist_ok=True)

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


def sh(cmd, check=False):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


# ==================== 1. CÀI ĐẶT (tối giản — KHÔNG xformers/torchcodec) ====================
print("=" * 60, "\n[1/4] Cai dat toi gian + tai ma nguon PE-Core\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q einops timm huggingface_hub ftfy regex 'huggingface_hub[hf_xet]' pyarrow pandas")

# tải 5 file core cần thiết trực tiếp từ repo Meta (tránh cài -e . nặng, tránh xformers/torchcodec)
CORE = PE_SRC / "core" / "vision_encoder"
CORE.mkdir(parents=True, exist_ok=True)
(PE_SRC / "core" / "__init__.py").touch()
(CORE / "__init__.py").touch()
BASE_URL = "https://raw.githubusercontent.com/facebookresearch/perception_models/main/core/vision_encoder"
for f in ["pe.py", "transforms.py", "tokenizer.py", "rope.py", "config.py"]:
    sh(f"curl -sL {BASE_URL}/{f} -o {CORE/f}")
sh(f"curl -sL {BASE_URL}/bpe_simple_vocab_16e6.txt.gz -o {CORE/'bpe_simple_vocab_16e6.txt.gz'}")
assert (CORE / "pe.py").stat().st_size > 5000, "Tai core/vision_encoder that bai — kiem tra Internet ON"
sys.path.insert(0, str(PE_SRC))

import torch
from PIL import Image
import core.vision_encoder.pe as pe
import core.vision_encoder.transforms as transforms

dev = "cuda" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev=='cuda' else 'KHONG CO GPU!'}", flush=True)

print(f"  Nap {MODEL_NAME} (tai checkpoint HF — ~2.7GB cho L, ~9.7GB cho G — lan dau se lau)...", flush=True)
t0 = time.time()
model = pe.CLIP.from_config(MODEL_NAME, pretrained=True)
model = model.to(dev).half().eval()
preprocess = transforms.get_image_transform(model.image_size)
print(f"  --> nap xong {time.time()-t0:.1f}s | image_size={model.image_size}", flush=True)


@torch.no_grad()
def encode_images(pil_list):
    batch = torch.stack([preprocess(im) for im in pil_list]).to(dev).half()
    feat = model.encode_image(batch, normalize=True)
    return feat.float().cpu().numpy().astype(np.float16)


# ==================== 2. GOM DANH SÁCH KEYFRAME (theo maps CSV) ====================
print("=" * 60, "\n[2/4] Gom danh sach keyframe\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
map_roots = glob.glob(MAP_ROOT_GLOB, recursive=True)
if not kf_roots:
    raise FileNotFoundError("Khong thay thu muc 'keyframes' trong /kaggle/input — nho Add dataset tu notebook 01.")

# CHIA VIEC cho nhieu account (tuy chon): dat SHARDS="L21_a,L22_a,..." de account nay CHI xu ly
# vai shard trong danh sach (cac account khac chay cung script voi SHARDS khac nhau, song song).
# De trong (mac dinh) = xu ly HET moi shard tim thay.
_SHARDS_FILTER = [s.strip() for s in os.environ.get("SHARDS", "").split(",") if s.strip()]
if _SHARDS_FILTER:
    before = len(map_roots)
    map_roots = [m for m in map_roots if Path(m).parent.name in _SHARDS_FILTER]
    print(f"  SHARDS filter: {_SHARDS_FILTER} -> giu {len(map_roots)}/{before} thu muc maps", flush=True)

print(f"  keyframes roots: {kf_roots}", flush=True)

items = []   # (video, n, frame_idx, img_path)
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
            imgs.append(Image.new("RGB", (model.image_size, model.image_size)))
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
info = {"model": MODEL_NAME, "tag": TAG, "n": len(items), "dim": int(out.shape[1]),
        "dtype": "float16", "minutes": round((time.time() - t0) / 60, 1)}
json.dump(info, open(OUT / "emb_info.json", "w"), indent=2)
mb = (OUT / f"feat_{TAG}.npy").stat().st_size / 1e6
print(f"  feat_{TAG}.npy: {out.shape} ({mb:.0f} MB) | {info['minutes']} phut", flush=True)
print("\n>>> XONG. Save Version -> tao Dataset 'aic-feat-pecore-<shard>'.", flush=True)
print(">>> feat_index.parquet giu (video,n,frame_idx) song song tung vector — dung de join khi search.", flush=True)

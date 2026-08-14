"""
================================================================================
KAGGLE NOTEBOOK 02 — ENCODE EMBEDDING (MetaCLIP-2) từ keyframe đã trích
================================================================================
Chạy SAU notebook 01. KHÔNG cần video — chỉ cần keyframe dataset (nhẹ) → nhanh.

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (hoặc P100)
  - Internet    : ON  (để pip install transformers mới + tải model MetaCLIP-2 lần đầu)
  - Add Input   : (các) dataset keyframe từ notebook 01 (VD aic-kf-L21a, hoặc nhiều shard)

MODEL (đổi ở biến MODEL_ID nếu A/B):
  - MetaCLIP-2 (mặc định, đa ngữ → KHỎI dịch tiếng Việt): facebook/metaclip-2-worldwide-huge-378
  - Bản NẶNG NHẤT (4B tham số, ViT-bigG-14-378): facebook/metaclip-2-worldwide-giant-378
    -> đặt env MODEL_ID=facebook/metaclip-2-worldwide-giant-378 và TAG=metaclip2giant (KHÔNG dùng
       lại TAG=metaclip2 vì đây là nhánh khác, giữ song song để A/B/tránh ghi đè feat cũ).
    -> checkpoint này CẦN transformers cài từ git source (script tự phát hiện qua MODEL_ID và cài
       đúng bản), và dùng bfloat16 (an toàn số học hơn float16 với model to, script tự chuyển).
    -> nên hạ BATCH xuống (VD BATCH=16) vì model to hơn nhiều, VRAM T4 15GB dễ tràn nếu giữ BATCH=64.
  - A/B khác: đổi MODEL_ID + BACKEND (xem dưới)

CHẠY SONG SONG NHIỀU ACCOUNT KAGGLE (VD 4 account rảnh):
  - Notebook 01 đã chia sẵn keyframe thành dataset aic-kf-account0..account4 (mỗi cái ~3 shard) hoặc
    aic-kf-<shard> riêng lẻ — chia đều 14 shard cho 4 notebook (VD mỗi notebook Add 3-4 dataset shard
    khác nhau), mỗi notebook chạy độc lập với cùng MODEL_ID=...giant-378, TAG=metaclip2giant.
  - Mỗi notebook ra 1 dataset output riêng (VD aic-feat-giant-p1..p4) — tải cả 4 về máy, gộp bằng
    cách nối (concat theo đúng thứ tự) feat_metaclip2giant.npy + feat_index.parquet của từng phần
    (giống cách đã gộp objects_all.jsonl/captions_*.jsonl nhiều account trước đây), rồi build lại
    FAISS index (indexing/build_faiss.py) cho collection mới.

ĐẦU RA (/kaggle/working/emb → Save Version → Kaggle Dataset "aic-feat-<shard>"):
  feat_<tag>.npy        (N, D) float16 — vector ẢNH, ĐÃ L2-normalize
  feat_index.parquet    N dòng: video, n, frame_idx  — song song từng vector (để join)
  emb_info.json
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path
import numpy as np

VERSION = "02-embed v1 (MetaCLIP-2)"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_ID = os.environ.get("MODEL_ID", "facebook/metaclip-2-worldwide-huge-378")
TAG      = os.environ.get("TAG", "metaclip2")   # tên file feature
BATCH    = int(os.environ.get("BATCH", "64"))
KF_ROOT_GLOB = "/kaggle/input/**/keyframes"     # dò thư mục keyframes trong mọi dataset đã add
MAP_ROOT_GLOB = "/kaggle/input/**/maps"

WORK = Path("/kaggle/working"); OUT = WORK / "emb"; OUT.mkdir(parents=True, exist_ok=True)

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


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/4] Cài đặt + nạp MetaCLIP-2\n", "=" * 60, flush=True)
_IS_GIANT = "giant" in MODEL_ID.lower()
if _IS_GIANT:
    # checkpoint giant-378 (4B tham số) chưa lên bản release PyPI ổn định lúc viết script này —
    # cần cài transformers từ git source theo đúng model card HuggingFace.
    sh(f"{sys.executable} -m pip install -q -U 'git+https://github.com/huggingface/transformers.git' pyarrow pandas")
else:
    sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' pyarrow pandas")
sh(f"{sys.executable} -m pip install -q 'pillow==11.1.0'")  # GHIM bản ổn định — bản Pillow mới nhất
                                                              # (do -U kéo theo) bị lỗi thiếu PIL._typing._Ink

import torch
from PIL import Image
import transformers
print(f"  transformers = {transformers.__version__}", flush=True)

from transformers import AutoModel, AutoProcessor
dev = "cuda" if torch.cuda.is_available() else "cpu"
# giant-378 (4B) an toàn số học hơn ở bf16 (model card khuyến nghị); huge-378 giữ fp16 như đã đo ổn định.
_DTYPE = torch.bfloat16 if _IS_GIANT else torch.float16
try:
    proc = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID, torch_dtype=_DTYPE).to(dev).eval()
except Exception as e:
    raise RuntimeError(
        f"Không nạp được {MODEL_ID} ({type(e).__name__}: {e}). "
        f"MetaCLIP-2 cần transformers rất mới — thử 'Restart & Run All' sau khi pip -U, "
        f"hoặc kiểm tra tên checkpoint trên HuggingFace.")
print(f"  model trên {dev} | {torch.cuda.get_device_name(0) if dev=='cuda' else ''} | dtype={_DTYPE}", flush=True)


@torch.no_grad()
def encode_images(pil_list):
    inp = proc(images=pil_list, return_tensors="pt").to(dev)
    if dev == "cuda":
        inp = {k: (v.to(_DTYPE) if v.dtype == torch.float32 else v) for k, v in inp.items()}
    out = model.get_image_features(**inp)
    if torch.is_tensor(out):
        feat = out
    else:
        # transformers ban moi boc ket qua thanh ModelOutput thay vi tensor thang
        feat = getattr(out, "image_embeds", None)
        if feat is None:
            feat = getattr(out, "pooler_output", None)
        if feat is None:
            feat = out.last_hidden_state[:, 0, :]  # fallback cuoi: CLS token
    feat = feat / feat.norm(dim=-1, keepdim=True).clamp_min(1e-8)
    return feat.float().cpu().numpy().astype(np.float16)


# ==================== 2. GOM DANH SÁCH KEYFRAME (theo maps CSV) ====================
print("=" * 60, "\n[2/4] Gom danh sách keyframe\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
map_roots = glob.glob(MAP_ROOT_GLOB, recursive=True)
if not kf_roots:
    raise FileNotFoundError("Không thấy thư mục 'keyframes' trong /kaggle/input — nhớ Add dataset từ notebook 01.")
print(f"  keyframes roots: {kf_roots}", flush=True)

# đọc maps để có (video, n, frame_idx) + đường dẫn ảnh, GIỮ ĐÚNG THỨ TỰ để join sau
items = []   # (video, n, frame_idx, img_path)
for mroot in map_roots:
    for csv in sorted(glob.glob(os.path.join(mroot, "*.csv"))):
        video = Path(csv).stem
        # tìm thư mục ảnh của video này (trong 1 trong các kf_roots)
        img_dir = None
        for kr in kf_roots:
            d = os.path.join(kr, video)
            if os.path.isdir(d):
                img_dir = d; break
        if img_dir is None:
            continue
        with open(csv) as f:
            next(f)  # header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                n, frame_idx = int(parts[0]), int(parts[1])
                p = os.path.join(img_dir, f"{n:06d}.webp")
                if os.path.exists(p):
                    items.append((video, n, frame_idx, p))
print(f"  --> {len(items):,} keyframe sẽ encode", flush=True)
if not items:
    raise RuntimeError("0 keyframe khớp giữa maps/ và keyframes/ — kiểm tra dataset input.")


# ==================== 3. ENCODE ====================
print("=" * 60, "\n[3/4] Encode embedding\n", "=" * 60, flush=True)
feats = np.zeros((len(items), 0), dtype=np.float16)  # sẽ khởi tạo đúng dim ở batch đầu
out = None
t0 = time.time()
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    imgs = []
    for (_, _, _, p) in chunk:
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception:
            imgs.append(Image.new("RGB", (384, 384)))  # ảnh lỗi → đen (giữ căn chỉnh index)
    v = encode_images(imgs)
    if out is None:
        out = np.zeros((len(items), v.shape[1]), dtype=np.float16)
    out[bi:bi + len(v)] = v
    if (bi // BATCH) % 20 == 0:
        done = bi + len(v)
        r = done / (time.time() - t0)
        print(f"  {done:,}/{len(items):,} | {r:.0f} img/s | còn ~{(len(items)-done)/r/60:.1f} phút", flush=True)

np.save(OUT / f"feat_{TAG}.npy", out)

# ==================== 4. LƯU INDEX SONG SONG + INFO ====================
print("=" * 60, "\n[4/4] Lưu index + info\n", "=" * 60, flush=True)
import pandas as pd
df = pd.DataFrame([(v, n, fi) for (v, n, fi, _) in items], columns=["video", "n", "frame_idx"])
df.to_parquet(OUT / "feat_index.parquet")
info = {"model": MODEL_ID, "tag": TAG, "n": len(items), "dim": int(out.shape[1]),
        "dtype": "float16", "compute_dtype": str(_DTYPE), "minutes": round((time.time() - t0) / 60, 1)}
json.dump(info, open(OUT / "emb_info.json", "w"), indent=2)
mb = (OUT / f"feat_{TAG}.npy").stat().st_size / 1e6
print(f"  feat_{TAG}.npy: {out.shape} ({mb:.0f} MB) | {info['minutes']} phút", flush=True)
print("\n>>> XONG. Save Version → tạo Dataset 'aic-feat-<shard>'. Về máy: build FAISS index (indexing/build_faiss.py).", flush=True)
print(">>> feat_index.parquet giữ (video,n,frame_idx) song song từng vector — dùng để join khi search.", flush=True)

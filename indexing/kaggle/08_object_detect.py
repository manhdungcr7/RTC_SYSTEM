"""
================================================================================
KAGGLE NOTEBOOK 08 — OBJECT DETECTION + MÀU (YOLO26) cho TOÀN BỘ keyframe
================================================================================
Phát hiện vật thể (COCO 80 lớp) + màu chủ đạo mỗi vật thể + vị trí lưới (grid 4x4,
kiểu VISIONE) cho từng keyframe → phục vụ câu hỏi kiểu "tìm cảnh có xe máy màu đỏ".
Đã CHỐT YOLO26 thay Co-DETR — benchmark T4 THẬT: 1.7-11.8ms/ảnh (85-588 ảnh/s),
cả 182k ảnh chỉ ~36 phút (bản x, nặng nhất) — Co-DETR ước ~25-51 GIỜ, không đáng
đánh đổi độ chính xác nhỏ lấy chi phí lớn (xem NGHIEN_CUU_KIEN_TRUC.md).

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (hoặc P100)
  - Internet    : ON (cài `ultralytics` + tải weight YOLO26 lần đầu)
  - Add Input   : dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all)

Vì tốc độ dư dả (~36 phút/182k ảnh), KHÔNG cần chia account — 1 account chạy hết.

ĐẦU RA (/kaggle/working/objects → Save Version → Dataset "aic-objects-batch1"):
  objects_all.jsonl   moi dong: {"video","n","frame_idx",
                                  "objects":[{"cls","conf","box":[x1,y1,x2,y2],
                                              "grid":"2a","color":"red"}]}
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "08-object-yolo26 v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_NAME = os.environ.get("MODEL_NAME", "yolo26x.pt")   # n/s/m/l/x — x = chinh xac nhat
CONF_THRES = float(os.environ.get("CONF_THRES", "0.25"))
BATCH = int(os.environ.get("BATCH", "32"))
GRID_N = 4   # luoi 4x4 kieu VISIONE (token vi tri: hang+cot, VD "2a")

AUDIO_UNUSED = None
KF_ROOT_GLOB = "/kaggle/input/**/keyframes"
MAP_ROOT_GLOB = "/kaggle/input/**/maps"
_SHARDS_FILTER = [s.strip() for s in os.environ.get("SHARDS", "").split(",") if s.strip()]

WORK = Path("/kaggle/working"); OUT = WORK / "objects"; OUT.mkdir(parents=True, exist_ok=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/4] Cai dat + nap YOLO26\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q -U ultralytics pyarrow pandas")

import torch
import numpy as np
from PIL import Image
from ultralytics import YOLO

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

t0 = time.time()
model = YOLO(MODEL_NAME)
model.to(dev)
COCO_NAMES = model.names   # dict id -> ten lop (80 lop COCO)
print(f"  --> nap xong {MODEL_NAME} ({time.time()-t0:.1f}s) | {len(COCO_NAMES)} lop", flush=True)

# giai nen tar (chi keyframes+maps) neu dataset la ban gop
_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
if _SHARDS_FILTER:
    _tar_files = [tf for tf in _tar_files if Path(tf).stem in _SHARDS_FILTER]
if _tar_files:
    import tarfile
    LOCAL_KF = WORK / "kf_extracted"; LOCAL_KF.mkdir(parents=True, exist_ok=True)
    print(f"  Giai nen {len(_tar_files)} tar...", flush=True)
    for tf in _tar_files:
        with tarfile.open(tf) as t:
            members = [m for m in t.getmembers() if "/keyframes/" in m.name or "/maps/" in m.name]
            t.extractall(LOCAL_KF, members=members)
    KF_ROOT_GLOB, MAP_ROOT_GLOB = f"{LOCAL_KF}/**/keyframes", f"{LOCAL_KF}/**/maps"


# ==================== 2. GOM DANH SÁCH KEYFRAME ====================
print("=" * 60, "\n[2/4] Gom danh sach keyframe\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
map_roots = glob.glob(MAP_ROOT_GLOB, recursive=True)
if _SHARDS_FILTER:
    kf_roots = [k for k in kf_roots if Path(k).parent.name in _SHARDS_FILTER]
    map_roots = [m for m in map_roots if Path(m).parent.name in _SHARDS_FILTER]
if not kf_roots:
    raise FileNotFoundError("Khong thay 'keyframes' — nho Add dataset tu notebook 01.")

items = []  # (video, n, frame_idx, path)
for mroot in map_roots:
    for csv in sorted(glob.glob(os.path.join(mroot, "*.csv"))):
        video = Path(csv).stem
        img_dir = next((os.path.join(kr, video) for kr in kf_roots
                        if os.path.isdir(os.path.join(kr, video))), None)
        if img_dir is None:
            continue
        with open(csv) as f:
            next(f)
            for line in f:
                p = line.strip().split(",")
                if len(p) < 2:
                    continue
                n, frame_idx = int(p[0]), int(p[1])
                ip = os.path.join(img_dir, f"{n:06d}.webp")
                if os.path.exists(ip):
                    items.append((video, n, frame_idx, ip))
print(f"  --> {len(items):,} keyframe se detect", flush=True)
if not items:
    raise RuntimeError("0 keyframe tim thay.")


# ==================== 3. TIỆN ÍCH: MÀU CHỦ ĐẠO + Ô LƯỚI ====================
def dominant_color(img: Image.Image, box):
    """Mau chu dao (ten mau co ban) trong vung box, bang trung binh RGB + anh xa
    ve 1 trong ~11 mau co ban (nhanh, du dung cho loc theo mau trong truy van)."""
    x1, y1, x2, y2 = [int(v) for v in box]
    crop = img.crop((max(0, x1), max(0, y1), max(x1 + 1, x2), max(y1 + 1, y2))).resize((16, 16))
    arr = np.asarray(crop.convert("RGB")).reshape(-1, 3).mean(axis=0)
    r, g, b = arr
    basic = {
        "black": (0, 0, 0), "white": (255, 255, 255), "gray": (128, 128, 128),
        "red": (200, 30, 30), "orange": (230, 130, 30), "yellow": (220, 210, 40),
        "green": (40, 150, 60), "blue": (40, 80, 200), "purple": (130, 60, 160),
        "pink": (230, 130, 180), "brown": (110, 70, 40),
    }
    best, bd = "gray", 1e9
    for name, (br, bg, bb) in basic.items():
        d = (r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2
        if d < bd:
            bd, best = d, name
    return best


def grid_cell(box, w, h, n=GRID_N):
    """Token vi tri kieu VISIONE: hang (so) + cot (chu), tam box roi vao o nao trong luoi NxN."""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    col = min(n - 1, int(cx / w * n))
    row = min(n - 1, int(cy / h * n))
    return f"{row+1}{chr(ord('a')+col)}"   # VD "2a" = hang 2, cot a


# ==================== 4. CHẠY DETECT (BATCH) ====================
print("=" * 60, "\n[4/4] Chay YOLO26 (batch)\n", "=" * 60, flush=True)
OUT_JSONL = OUT / "objects_all.jsonl"
done_keys = set()
if OUT_JSONL.exists():
    for line in open(OUT_JSONL, encoding="utf-8"):
        d = json.loads(line)
        done_keys.add((d["video"], d["n"]))
items = [it for it in items if (it[0], it[1]) not in done_keys]
print(f"  --> {len(items):,} anh se chay ({len(done_keys):,} da xong tu truoc)", flush=True)

t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
n_done = 0
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    paths = [c[3] for c in chunk]
    results = model.predict(paths, conf=CONF_THRES, verbose=False, device=dev)

    for (video, n, frame_idx, p), res in zip(chunk, results):
        w, h = res.orig_shape[1], res.orig_shape[0]
        img = None
        objs = []
        boxes = res.boxes
        if boxes is not None and len(boxes) > 0:
            img = Image.open(p).convert("RGB")
            for b in boxes:
                xyxy = b.xyxy[0].tolist()
                cls_id = int(b.cls[0].item())
                conf = round(float(b.conf[0].item()), 3)
                objs.append({
                    "cls": COCO_NAMES[cls_id],
                    "conf": conf,
                    "box": [round(v, 1) for v in xyxy],
                    "grid": grid_cell(xyxy, w, h),
                    "color": dominant_color(img, xyxy),
                })
        fout.write(json.dumps({"video": video, "n": n, "frame_idx": frame_idx, "objects": objs},
                              ensure_ascii=False) + "\n")

    fout.flush()
    n_done += len(chunk)
    if (bi // BATCH) % 20 == 0:
        r = n_done / (time.time() - t0)
        eta = (len(items) - n_done) / max(r, 1e-6) / 60
        print(f"  {n_done:,}/{len(items):,} | {r:.1f} img/s | con ~{eta:.0f} phut", flush=True)
fout.close()

total = sum(1 for _ in open(OUT_JSONL, encoding="utf-8"))
print(f"\n  Xong: {total:,} dong | {(time.time()-t0)/60:.1f} phut", flush=True)
print("\n>>> XONG. Save Version -> Dataset 'aic-objects-batch1'.", flush=True)

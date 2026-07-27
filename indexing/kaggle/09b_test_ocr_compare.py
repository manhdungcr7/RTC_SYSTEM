"""
================================================================================
KAGGLE — TEST SO SÁNH: PaddleOCR-thuần vs PaddleOCR(detect)+VietOCR(recognize)
================================================================================
Chạy ~30 ảnh mẫu qua CẢ 2 cách, in ra cạnh nhau để tự mắt so sánh chất lượng đọc
tiếng Việt, đồng thời đo tốc độ thật của từng cách — quyết định dùng cách nào cho
notebook 09 chính thức TRƯỚC khi tốn GPU-giờ chạy hàng loạt 167,850 ảnh.

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON | Add Input: bất kỳ dataset keyframe nào
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

print(">>> test-ocr-compare v1", flush=True)
N_SAMPLE = int(os.environ.get("N_SAMPLE", "30"))

def sh(c, check=True):
    print(f"$ {c}", flush=True)
    r = subprocess.run(c, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout[-3000:], flush=True)
    if r.stderr.strip():
        print(r.stderr[-3000:], flush=True)
    if r.returncode != 0 and check:
        raise RuntimeError(f"LOI (exit {r.returncode}): {c}")
    return r


# DA XAC NHAN: index cu126 cua Baidu hay TIMEOUT tu mang Kaggle — dung thang PyPI
# mac dinh (da kiem chung nhan dung GPU T4 tren Kaggle).
print("  Cai paddlepaddle-gpu (ban PyPI mac dinh)...", flush=True)
sh(f"{sys.executable} -m pip install -q -U paddlepaddle-gpu")
try:
    import paddle
    assert paddle.device.is_compiled_with_cuda()
except Exception as e:
    print(f"  Van khong on ({e}) -> thu lai qua index cu126 (du cham)...", flush=True)
    sh(f"{sys.executable} -m pip install -q paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/")
    import importlib
    if "paddle" in sys.modules:
        importlib.reload(sys.modules["paddle"])
    else:
        import paddle

sh(f"{sys.executable} -m pip install -q paddleocr vietocr")
sh(f"{sys.executable} -m pip install -q 'pillow==10.4.0'")  # paddlex/PIL.ImageFont can is_directory
                                                              # trong PIL._util — da bi xoa tu Pillow 11+

import paddle
print(f"  GPU: {paddle.device.cuda.get_device_name(0) if paddle.device.is_compiled_with_cuda() else 'KHONG CO GPU! (se cham)'}", flush=True)

from paddleocr import PaddleOCR, TextDetection
from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg
from PIL import Image

# --- nap ca 3 (PaddleOCR thuan, PaddleOCR detect-only, VietOCR recognize) ---
t0 = time.time()
ocr_full = PaddleOCR(lang="vi", device="gpu:0", use_doc_orientation_classify=False,
                      use_doc_unwarping=False, use_textline_orientation=False)
print(f"  nap PaddleOCR-thuan: {time.time()-t0:.1f}s", flush=True)

t0 = time.time()
det_only = TextDetection()
vcfg = Cfg.load_config_from_name("vgg_transformer")
vcfg["cnn"]["pretrained"] = False
vcfg["device"] = "cuda:0"
recognizer = Predictor(vcfg)
print(f"  nap PaddleOCR-detect + VietOCR: {time.time()-t0:.1f}s", flush=True)

# --- lay mau anh ---
tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)[:1]
KF_GLOB, MAP_GLOB = "/kaggle/input/**/keyframes", "/kaggle/input/**/maps"
if tar_files:
    import tarfile
    LOCAL = Path("/kaggle/working/kf_sample"); LOCAL.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_files[0]) as t:
        members = [m for m in t.getmembers() if "/keyframes/" in m.name or "/maps/" in m.name]
        t.extractall(LOCAL, members=members)
    KF_GLOB, MAP_GLOB = f"{LOCAL}/**/keyframes", f"{LOCAL}/**/maps"

kf_roots = glob.glob(KF_GLOB, recursive=True)
map_roots = glob.glob(MAP_GLOB, recursive=True)
paths = []
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
                ip = os.path.join(img_dir, f"{int(p[0]):06d}.webp")
                if os.path.exists(ip):
                    paths.append(ip)
        if len(paths) >= N_SAMPLE * 3:   # lay du de sau loc con quan tam
            break
    if len(paths) >= N_SAMPLE * 3:
        break
print(f"  --> co {len(paths)} anh de thu, se chay {N_SAMPLE} anh dau", flush=True)
paths = paths[:N_SAMPLE]


def crop_box(img, poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x1, y1, x2, y2 = max(0, min(xs)), max(0, min(ys)), max(xs), max(ys)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return img.crop((x1, y1, x2, y2))


# --- chay CACH 1: PaddleOCR thuan ---
print("\n" + "=" * 70, "\nCACH 1: PaddleOCR thuan (tu doc chu)\n", "=" * 70, flush=True)
t0 = time.time()
res1_all = []
for p in paths:
    result = ocr_full.predict(p)
    texts = []
    for res in result:
        for t, sc in zip(res.get("rec_texts", []), res.get("rec_scores", [])):
            if sc >= 0.5 and t.strip():
                texts.append((t.strip(), round(float(sc), 2)))
    res1_all.append(texts)
t1_full = time.time() - t0
print(f"  Tong thoi gian: {t1_full:.1f}s | {len(paths)/t1_full:.2f} anh/s", flush=True)

# --- chay CACH 2: PaddleOCR detect + VietOCR recognize ---
print("\n" + "=" * 70, "\nCACH 2: PaddleOCR(detect) + VietOCR(recognize)\n", "=" * 70, flush=True)
t0 = time.time()
res2_all = []
for p in paths:
    det = det_only.predict(p, batch_size=1)
    texts = []
    img = None
    for res in det:
        for poly, sc in zip(res.get("dt_polys", []), res.get("dt_scores", [])):
            if sc < 0.5:
                continue
            if img is None:
                img = Image.open(p).convert("RGB")
            crop = crop_box(img, poly)
            if crop is None:
                continue
            try:
                text = recognizer.predict(crop).strip()
            except Exception:
                text = ""
            if text:
                texts.append((text, round(float(sc), 2)))
    res2_all.append(texts)
t1_hybrid = time.time() - t0
print(f"  Tong thoi gian: {t1_hybrid:.1f}s | {len(paths)/t1_hybrid:.2f} anh/s", flush=True)

# --- in canh nhau de so sanh ---
print("\n" + "=" * 70, "\nSO SANH TUNG ANH\n", "=" * 70, flush=True)
for i, p in enumerate(paths):
    print(f"\n[{i}] {Path(p).name}", flush=True)
    print(f"  Cach1 (PaddleOCR thuan): {res1_all[i]}", flush=True)
    print(f"  Cach2 (Paddle+VietOCR) : {res2_all[i]}", flush=True)

print("\n" + "=" * 70, flush=True)
print(f"TOM TAT TOC DO: Cach1={len(paths)/t1_full:.2f} anh/s | Cach2={len(paths)/t1_hybrid:.2f} anh/s", flush=True)
print(">>> XONG. Doc ky phan so sanh tung anh o tren de tu danh gia chat luong.", flush=True)

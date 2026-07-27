"""
================================================================================
KAGGLE NOTEBOOK 09 — OCR (PaddleOCR tách vùng chữ + VietOCR đọc chữ) cho keyframe
================================================================================
Đọc chữ trên màn hình (băng rôn/phụ đề/biển hiệu/logo...) cho từng keyframe.

VÌ SAO 2 model ghép lại (không dùng PaddleOCR thuần, không dùng PARSeq-VN):
- PARSeq fine-tune tiếng Việt: weight chỉ có trên Google Drive CÁ NHÂN — rủi ro
  link hỏng khi chạy hàng loạt, loại.
- PaddleOCR THUẦN (tự đọc chữ luôn): phần TÁCH VÙNG CHỮ (detection) không phụ
  thuộc ngôn ngữ nên rất đáng tin, nhưng phần ĐỌC CHỮ (recognition) đa ngôn ngữ
  chung của PaddleOCR không chuyên cho tiếng Việt.
- Tín hiệu thực tế: nhiều pipeline OCR tiếng Việt (VD vitmetmoi/Vietnamese-OCR)
  ghép PaddleOCR (detect) + VietOCR (recognize, huấn luyện riêng tiếng Việt,
  package pip chính thức pbcquoc/vietocr) — dùng đúng công thức này.
⚠️ Chưa có benchmark số liệu trực tiếp so cách này với PaddleOCR thuần trên scene-
text tiếng Việt — xem `09b_test_ocr_compare.py` để tự test trước khi tin tưởng.

QUAN TRỌNG — đã loại `L25_a1` và `L25_b` khỏi danh sách xử lý: 2 shard này TRÙNG
LẶP HOÀN TOÀN với `L25_a` (đã xác nhận MD5 khớp 2 mẫu khi giải nén video — chưa
kiểm tra hết cả 88 video, nhưng bằng chứng cấu trúc phạm vi file khớp khít).

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2
  - Internet    : ON (cài paddleocr + paddlepaddle-gpu + vietocr, tải model lần đầu)
  - Add Input   : dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all)

CHIA 3 ACCOUNT (cân bằng theo SỐ KEYFRAME thật, đã loại trùng lặp):
  ACCOUNT = "1" -> 56,028 kf  (L22_a, L25_a, L26_a, L24_a, L23_a)
  ACCOUNT = "2" -> 54,390 kf  (L26_c, L26_b, L28_a, L29_a)
  ACCOUNT = "3" -> 57,432 kf  (L26_d, L26_e, L21_a, L30_a, L27_a)

ĐẦU RA (/kaggle/working/ocr → Save Version → Dataset "aic-ocr-<ACCOUNT>"):
  ocr_<ACCOUNT>.jsonl   moi dong: {"video","n","frame_idx",
                                    "texts":[{"text","det_conf","box":[[x,y]x4]}]}
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "09-ocr-paddle-vietocr v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
DET_CONF_THRES = float(os.environ.get("DET_CONF_THRES", "0.5"))
VIETOCR_CONFIG = os.environ.get("VIETOCR_CONFIG", "vgg_transformer")  # hoac 'vgg_seq2seq' (nhanh hon)

ACCOUNT_GROUPS = {
    "1": ["L22_a", "L25_a", "L26_a", "L24_a", "L23_a"],
    "2": ["L26_c", "L26_b", "L28_a", "L29_a"],
    "3": ["L26_d", "L26_e", "L21_a", "L30_a", "L27_a"],
}
DUP_SKIP = {"L25_a1", "L25_b"}   # trung lap L25_a — KHONG BAO GIO xu ly

ACCOUNT = os.environ.get("ACCOUNT", "1")   # <<< SUA O DAY: "1" / "2" / "3"
if ACCOUNT in ACCOUNT_GROUPS:
    SHARDS = ACCOUNT_GROUPS[ACCOUNT]
elif ACCOUNT.strip():
    SHARDS = [s.strip() for s in ACCOUNT.split(",") if s.strip() and s.strip() not in DUP_SKIP]
else:
    SHARDS = []
print(f"  ACCOUNT={ACCOUNT!r} --> {len(SHARDS)} shard: {SHARDS}", flush=True)

KF_ROOT_GLOB = "/kaggle/input/**/keyframes"
MAP_ROOT_GLOB = "/kaggle/input/**/maps"

WORK = Path("/kaggle/working"); OUT = WORK / "ocr"; OUT.mkdir(parents=True, exist_ok=True)
OUT_JSONL = OUT / f"ocr_{ACCOUNT}.jsonl"


def sh(cmd, check=True):
    print(f"$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout[-3000:], flush=True)
    if r.stderr.strip():
        print(r.stderr[-3000:], flush=True)
    if r.returncode != 0 and check:
        raise RuntimeError(f"LOI (exit {r.returncode}): {cmd}")
    return r


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/4] Cai dat + nap PaddleOCR(detect) + VietOCR(recognize)\n", "=" * 60, flush=True)
# DA XAC NHAN: index cu126 cua Baidu (paddle-whl.bj.bcebos.com) hay TIMEOUT tu mang
# Kaggle (~13 phut cho troi) — dung thang ban PyPI mac dinh, da kiem chung nhan
# dung GPU T4 tren Kaggle, khong can thu cu126 nua.
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

sh(f"{sys.executable} -m pip install -q paddleocr vietocr pyarrow pandas")
sh(f"{sys.executable} -m pip install -q 'pillow==10.4.0'")  # paddlex/PIL.ImageFont can 'is_directory'
                                                              # trong PIL._util — da bi XOA tu Pillow 11+,
                                                              # ghim 10.4.0 (ban cuoi con giu ham nay)

print(f"  Paddle GPU: {paddle.device.is_compiled_with_cuda()} | "
      f"{paddle.device.cuda.get_device_name(0) if paddle.device.is_compiled_with_cuda() else 'KHONG CO GPU!'}",
      flush=True)

from paddleocr import TextDetection
from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg
from PIL import Image

t0 = time.time()
detector = TextDetection()   # chi tach vung chu, khong doc chu (khong phu thuoc ngon ngu)

vcfg = Cfg.load_config_from_name(VIETOCR_CONFIG)
vcfg["cnn"]["pretrained"] = False
vcfg["device"] = "cuda:0"
recognizer = Predictor(vcfg)   # doc chu tieng Viet
print(f"  --> nap xong ca 2 model ({time.time()-t0:.1f}s)", flush=True)

# giai nen tar (chi keyframes+maps)
_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
if SHARDS:
    _tar_files = [tf for tf in _tar_files if Path(tf).stem in SHARDS]
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
if SHARDS:
    kf_roots = [k for k in kf_roots if Path(k).parent.name in SHARDS]
    map_roots = [m for m in map_roots if Path(m).parent.name in SHARDS]
if not kf_roots:
    raise FileNotFoundError("Khong thay 'keyframes' — nho Add dataset tu notebook 01 + dung ACCOUNT.")

items = []
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
print(f"  --> {len(items):,} keyframe se OCR", flush=True)
if not items:
    raise RuntimeError("0 keyframe tim thay.")

done_keys = set()
if OUT_JSONL.exists():
    for line in open(OUT_JSONL, encoding="utf-8"):
        d = json.loads(line)
        done_keys.add((d["video"], d["n"]))
items = [it for it in items if (it[0], it[1]) not in done_keys]
print(f"  --> con {len(items):,} keyframe can OCR ({len(done_keys):,} da xong tu truoc)", flush=True)


# ==================== 3. HÀM XỬ LÝ 1 ẢNH ====================
def crop_box(img: Image.Image, poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x1, y1, x2, y2 = max(0, min(xs)), max(0, min(ys)), max(xs), max(ys)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    return img.crop((x1, y1, x2, y2))


def ocr_one(path):
    det = detector.predict(path, batch_size=1)
    texts = []
    img = None
    for res in det:
        polys = res.get("dt_polys", [])
        scores = res.get("dt_scores", [])
        for poly, sc in zip(polys, scores):
            if sc < DET_CONF_THRES:
                continue
            if img is None:
                img = Image.open(path).convert("RGB")
            crop = crop_box(img, poly)
            if crop is None:
                continue
            try:
                text = recognizer.predict(crop)
            except Exception:
                continue
            text = (text or "").strip()
            if text:
                texts.append({"text": text, "det_conf": round(float(sc), 3),
                              "box": [[round(float(x), 1), round(float(y), 1)] for x, y in poly]})
    return texts


# ==================== 4. CHẠY OCR ====================
print("=" * 60, "\n[4/4] Chay OCR (detect + recognize)\n", "=" * 60, flush=True)
t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
n_done = 0
n_errors = 0
for video, n, frame_idx, p in items:
    try:
        texts = ocr_one(p)
        fout.write(json.dumps({"video": video, "n": n, "frame_idx": frame_idx, "texts": texts},
                              ensure_ascii=False) + "\n")
    except Exception as ex:
        n_errors += 1
        fout.write(json.dumps({"video": video, "n": n, "frame_idx": frame_idx, "texts": [],
                              "error": str(ex)[:150]}, ensure_ascii=False) + "\n")

    n_done += 1
    if n_done % 500 == 0:
        fout.flush()
        r = n_done / (time.time() - t0)
        eta = (len(items) - n_done) / max(r, 1e-6) / 60
        print(f"  {n_done:,}/{len(items):,} | {r:.1f} img/s | loi: {n_errors} | con ~{eta:.0f} phut", flush=True)
fout.close()

total = sum(1 for _ in open(OUT_JSONL, encoding="utf-8"))
print("=" * 60, "\n[Xong]\n", "=" * 60, flush=True)
print(f"  ocr_{ACCOUNT}.jsonl: {total:,} dong | {(time.time()-t0)/60:.1f} phut lan nay | loi: {n_errors}", flush=True)
print(f"\n>>> XONG. Save Version -> Dataset 'aic-ocr-{ACCOUNT}'.", flush=True)
print(">>> Neu chua het (session het gio): chay lai notebook — tu bo qua phan da xong.", flush=True)

"""
================================================================================
KAGGLE NOTEBOOK 09 — OCR (PaddleOCR, tiếng Việt) cho keyframe
================================================================================
Đọc chữ trên màn hình (băng rôn/phụ đề/biển hiệu/logo...) cho từng keyframe.

VÌ SAO PaddleOCR (không phải PARSeq-VN như bàn ban đầu): bản PARSeq fine-tune
tiếng Việt tìm được (`lynguyenminh/vietnamese-scenetext-detection-recognition`)
chỉ lưu trên Google Drive CÁ NHÂN — rủi ro link hỏng/giới hạn tải khi chạy hàng
loạt trên Kaggle, không có gì đảm bảo. PaddleOCR (Baidu, dự án lớn, bảo trì tích
cực) có **hỗ trợ tiếng Việt sẵn** (`lang="vi"`), hosting chính thức đáng tin cậy,
end-to-end (detect+recognize gộp 1 lời gọi) — đánh đổi nhỏ về chất lượng lý
thuyết để lấy độ ổn định chắc chắn hơn nhiều.

QUAN TRỌNG — đã loại `L25_a1` và `L25_b` khỏi danh sách xử lý: 2 shard này TRÙNG
LẶP HOÀN TOÀN với `L25_a` (đã xác nhận MD5 khớp 100% khi giải nén video) — xử lý
sẽ chỉ lãng phí GPU-giờ vô ích, không thêm dữ liệu mới.

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2
  - Internet    : ON (cài paddleocr + paddlepaddle-gpu, tải model tiếng Việt lần đầu)
  - Add Input   : dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all)

CHIA 3 ACCOUNT (cân bằng theo SỐ KEYFRAME thật, đã loại trùng lặp):
  ACCOUNT = "1" -> 56,028 kf  (L22_a, L25_a, L26_a, L24_a, L23_a)
  ACCOUNT = "2" -> 54,390 kf  (L26_c, L26_b, L28_a, L29_a)
  ACCOUNT = "3" -> 57,432 kf  (L26_d, L26_e, L21_a, L30_a, L27_a)

ĐẦU RA (/kaggle/working/ocr → Save Version → Dataset "aic-ocr-<ACCOUNT>"):
  ocr_<ACCOUNT>.jsonl   moi dong: {"video","n","frame_idx",
                                    "texts":[{"text","conf","box":[[x,y]x4]}]}
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "09-ocr-paddleocr v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
CONF_THRES = float(os.environ.get("CONF_THRES", "0.5"))

# CHIA 3 ACCOUNT — cân bằng theo keyframe THẬT, L25_a1/L25_b bị loại vi trung lap voi L25_a
ACCOUNT_GROUPS = {
    "1": ["L22_a", "L25_a", "L26_a", "L24_a", "L23_a"],
    "2": ["L26_c", "L26_b", "L28_a", "L29_a"],
    "3": ["L26_d", "L26_e", "L21_a", "L30_a", "L27_a"],
}
DUP_SKIP = {"L25_a1", "L25_b"}   # trung lap L25_a — KHONG BAO GIO xu ly du ACCOUNT gi

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


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/4] Cai dat + nap PaddleOCR (tieng Viet)\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/")
sh(f"{sys.executable} -m pip install -q paddleocr pyarrow pandas")

import paddle
print(f"  Paddle GPU: {paddle.device.is_compiled_with_cuda()} | "
      f"{paddle.device.cuda.get_device_name(0) if paddle.device.is_compiled_with_cuda() else 'KHONG CO GPU!'}",
      flush=True)

from paddleocr import PaddleOCR

t0 = time.time()
ocr = PaddleOCR(lang="vi", device="gpu:0", use_doc_orientation_classify=False,
                 use_doc_unwarping=False, use_textline_orientation=False)
print(f"  --> nap xong PaddleOCR ({time.time()-t0:.1f}s)", flush=True)

# giai nen tar (chi keyframes+maps, dung SHARDS de chi giai nen dung phan can)
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
print(f"  --> {len(items):,} keyframe se OCR", flush=True)
if not items:
    raise RuntimeError("0 keyframe tim thay.")

# RESUMABLE
done_keys = set()
if OUT_JSONL.exists():
    for line in open(OUT_JSONL, encoding="utf-8"):
        d = json.loads(line)
        done_keys.add((d["video"], d["n"]))
items = [it for it in items if (it[0], it[1]) not in done_keys]
print(f"  --> con {len(items):,} keyframe can OCR ({len(done_keys):,} da xong tu truoc)", flush=True)


# ==================== 3. CHẠY OCR ====================
print("=" * 60, "\n[3/4] Chay OCR\n", "=" * 60, flush=True)
t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
n_done = 0
n_errors = 0
for video, n, frame_idx, p in items:
    try:
        result = ocr.predict(p)
        texts = []
        for res in result:
            rec_texts = res.get("rec_texts", [])
            rec_scores = res.get("rec_scores", [])
            rec_polys = res.get("rec_polys", [])
            for t, sc, box in zip(rec_texts, rec_scores, rec_polys):
                if sc >= CONF_THRES and t.strip():
                    texts.append({"text": t.strip(), "conf": round(float(sc), 3),
                                  "box": [[round(float(x), 1), round(float(y), 1)] for x, y in box]})
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


# ==================== 4. TỔNG KẾT ====================
total = sum(1 for _ in open(OUT_JSONL, encoding="utf-8"))
print("=" * 60, "\n[4/4] Xong\n", "=" * 60, flush=True)
print(f"  ocr_{ACCOUNT}.jsonl: {total:,} dong | {(time.time()-t0)/60:.1f} phut lan nay | loi: {n_errors}", flush=True)
print(f"\n>>> XONG. Save Version -> Dataset 'aic-ocr-{ACCOUNT}'.", flush=True)
print(">>> Neu chua het (session het gio): chay lai notebook — tu bo qua phan da xong.", flush=True)

"""
================================================================================
KAGGLE NOTEBOOK 09 — OCR bằng Qwen3-VL-4B (thay PaddleOCR+VietOCR)
================================================================================
Đọc chữ trên màn hình (băng rôn/phụ đề/biển hiệu/logo...) bằng chính Qwen3-VL-4B
đã dùng cho caption (07_caption_qwen3vl.py) — CHỈ đổi prompt sang "chỉ liệt kê
chữ nhìn thấy", không mô tả cảnh.

VÌ SAO đổi từ PaddleOCR+VietOCR sang VLM:
- PaddleOCR+VietOCR gặp 3 lỗi liên tiếp khi setup trên Kaggle: (1) index cu126
  Baidu timeout, (2) xung đột phiên bản Pillow (vietocr ép cứng ==10.2.0, paddlex
  cần is_directory đã bị Pillow 11+ xoá), (3) paddlex/paddlepaddle KHÔNG khớp API
  (`set_optimization_level` không tồn tại) — đây là BUG CỘNG ĐỒNG CHƯA CÓ FIX
  (issue mở trên GitHub PaddleOCR, không rõ khi nào sửa).
- Qwen3-VL-4B đã CHẠY ỔN ĐỊNH thật (đang dùng cho caption, không lỗi dependency
  nào) và ĐÃ THẤY BẰNG MẮT nó đọc đúng chữ tiếng Việt có dấu trong caption đã có
  (VD "MÓN NGON mỗi ngày", "NGUYÊN LIỆU") — không phải suy đoán.
- OCRBench Qwen3-VL-4B = 88.1% (đo được, không phải "nghe nói").
- Đội vô địch OpenCubee cũng dùng chung 1 model Qwen cho cả caption VÀ OCR.

⚠️ Đánh đổi: KHÔNG có toạ độ box chính xác từng chữ (chỉ liệt kê CÓ chữ gì, không
định vị pixel — object detection notebook 08 đã lo phần định vị không gian rồi).

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON
Add Input: dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all)

CHIA 5 ACCOUNT (cân bằng theo keyframe THẬT tu shard_info.json, da loai L25_a1/L25_b trung L25_a):
  ACCOUNT = "1" -> 35,150 kf  (L22_a, L29_a, L30_a)
  ACCOUNT = "2" -> 35,809 kf  (L26_c, L28_a, L24_a)
  ACCOUNT = "3" -> 34,160 kf  (L26_d, L21_a, L27_a)
  ACCOUNT = "4" -> 33,022 kf  (L26_e, L26_a, L23_a)
  ACCOUNT = "5" -> 29,709 kf  (L26_b, L25_a)

ĐẦU RA (/kaggle/working/ocr → Save Version → Dataset "aic-ocr-<ACCOUNT>"):
  ocr_<ACCOUNT>.jsonl   moi dong: {"video","n","frame_idx","texts": "..." }
                        (texts = chuoi Qwen liet ke, "" hoac "NO_TEXT" neu khong co chu)
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "09-ocr-qwen3vl v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-VL-4B-Instruct")
BATCH = int(os.environ.get("BATCH", "32"))   # DO THAT: account 2 chay batch=32 on dinh, khong OOM, 1.7 img/s
MAX_TOK = int(os.environ.get("MAX_TOK", "64"))   # DO THAT tren 30 anh mau (09b_test_ocr_qwen_length.py):
                                                    # median=14, p90=32, chi 1/30 cham tran 150 (bang
                                                    # credit/nguyen-lieu day chu) -> 64 du margin ~2x p90.
                                                    # QUAN TRONG: generate theo BATCH doi hang CHAM NHAT
                                                    # moi xong -> 1 anh dai trong batch keo ca batch len
                                                    # gan tran -> tran cao (150) lam tot toc do THAT rat
                                                    # nhieu (do duoc 0.6-0.8 img/s, cham hon caption han).
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", str(384 * 384)))
MIN_PIXELS = int(os.environ.get("MIN_PIXELS", str(128 * 128)))
PROMPT = os.environ.get("PROMPT",
    "Read and transcribe ALL text visible in this image exactly as written, "
    "preserving Vietnamese diacritics and original casing. List each distinct "
    "piece of text on its own line, in reading order (top to bottom, left to "
    "right). Do NOT describe the image or add any commentary — output ONLY the "
    "transcribed text. If there is no visible text anywhere in the image, "
    "respond with exactly: NO_TEXT")

ACCOUNT_GROUPS = {
    "1": ["L22_a", "L29_a", "L30_a"],
    "2": ["L26_c", "L28_a", "L24_a"],
    "3": ["L26_d", "L21_a", "L27_a"],
    "4": ["L26_e", "L26_a", "L23_a"],
    "5": ["L26_b", "L25_a"],
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

WORK = Path("/kaggle/working"); OUT = WORK / "ocr"; OUT.mkdir(parents=True, exist_ok=True)
OUT_JSONL = OUT / f"ocr_{ACCOUNT}.jsonl"


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/4] Cai dat + nap Qwen3-VL-4B\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' accelerate qwen-vl-utils")
sh(f"{sys.executable} -m pip install -q 'pillow==11.1.0'")   # da xac nhan on cho script nay (khac 09b)

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

t0 = time.time()
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID, dtype=torch.float16, attn_implementation="sdpa", device_map={"": dev}).eval()
processor = AutoProcessor.from_pretrained(MODEL_ID, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
processor.tokenizer.padding_side = "left"
print(f"  --> nap xong {MODEL_ID} ({time.time()-t0:.1f}s)", flush=True)

_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
if SHARDS:
    _tar_files = [tf for tf in _tar_files if Path(tf).stem in SHARDS]
KF_ROOT_GLOB, MAP_ROOT_GLOB = "/kaggle/input/**/keyframes", "/kaggle/input/**/maps"
if _tar_files:
    import tarfile
    LOCAL_KF = WORK / "kf_extracted"; LOCAL_KF.mkdir(parents=True, exist_ok=True)
    print(f"  Giai nen {len(_tar_files)} tar (keyframes+maps)...", flush=True)
    for i, tf in enumerate(_tar_files):
        t0e = time.time()
        with tarfile.open(tf) as t:
            members = [m for m in t.getmembers() if "/keyframes/" in m.name or "/maps/" in m.name]
            t.extractall(LOCAL_KF, members=members)
        print(f"  [{i+1}/{len(_tar_files)}] {Path(tf).name} ({time.time()-t0e:.1f}s)", flush=True)
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


# ==================== 3. OCR THEO BATCH ====================
print("=" * 60, "\n[3/4] OCR (batch)\n", "=" * 60, flush=True)


@torch.no_grad()
def ocr_batch(paths):
    messages = [[{"role": "user", "content": [
        {"type": "image", "image": f"file://{p}", "min_pixels": MIN_PIXELS, "max_pixels": MAX_PIXELS},
        {"type": "text", "text": PROMPT}]}] for p in paths]
    texts_in = [processor.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in messages]
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(text=texts_in, images=image_inputs, padding=True, return_tensors="pt").to(dev)
    gen = model.generate(**inputs, max_new_tokens=MAX_TOK, do_sample=False, use_cache=True,
                          repetition_penalty=1.3, no_repeat_ngram_size=3)   # chan lap vong lap
                          # (batch1 phat hien 41.7% cac anh chu day dac bi lap khi chua co 2 tham
                          # so nay — xem 09c_fix_truncated_ocr.py; giu lai cho batch sau, khong can
                          # chay lai batch1 vi ty le loi thap va da co fix rieng cho phan duoi)
    trimmed = gen[:, inputs.input_ids.shape[1]:]
    outs = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return [o.strip() for o in outs]


t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
n_done = 0
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    try:
        outs = ocr_batch([c[3] for c in chunk])
    except Exception as ex:
        print(f"  [batch {bi} loi: {type(ex).__name__} {str(ex)[:80]}] -> fallback tung anh", flush=True)
        outs = []
        for c in chunk:
            try:
                outs.append(ocr_batch([c[3]])[0])
            except Exception:
                outs.append("")
    for (video, n, frame_idx, _), out_text in zip(chunk, outs):
        texts = "" if out_text.strip().upper() == "NO_TEXT" else out_text
        fout.write(json.dumps({"video": video, "n": n, "frame_idx": frame_idx, "texts": texts},
                              ensure_ascii=False) + "\n")
    fout.flush()
    n_done += len(chunk)
    if (bi // BATCH) % 20 == 0:
        r = n_done / (time.time() - t0)
        eta = (len(items) - n_done) / max(r, 1e-6) / 60
        print(f"  {n_done:,}/{len(items):,} | {r:.1f} img/s | con ~{eta:.0f} phut", flush=True)
fout.close()


# ==================== 4. TỔNG KẾT ====================
total = sum(1 for _ in open(OUT_JSONL, encoding="utf-8"))
print("=" * 60, "\n[4/4] Xong\n", "=" * 60, flush=True)
print(f"  ocr_{ACCOUNT}.jsonl: {total:,} dong | {(time.time()-t0)/60:.1f} phut lan nay", flush=True)
print(f"\n>>> XONG. Save Version -> Dataset 'aic-ocr-{ACCOUNT}'.", flush=True)
print(">>> Neu chua het (session het gio): chay lai notebook — tu bo qua phan da xong.", flush=True)

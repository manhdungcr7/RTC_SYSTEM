"""
================================================================================
KAGGLE — SỬA OCR bị cắt cụt (MAX_TOK=64 không đủ cho 168 ảnh chữ dày đặc)
================================================================================
09_ocr_qwen3vl.py chạy xong 167,850 ảnh, kiểm tra thấy 168 ảnh (0.1%) bị cắt cụt
do chạm trần MAX_TOK=64 — toàn bộ là khung hình chứa văn bản dày đặc kiểu chứng
chỉ/certificate (IACBE, IELTS, WHO...), khác hẳn nội dung video nấu ăn thông
thường. Danh sách 168 key (video, n) đã xác định CHÍNH XÁC từ dữ liệu thật (không
đoán), nhúng thẳng vào script — không cần upload thêm dataset ocr cũ.

v2: lần chạy đầu (chỉ tăng MAX_TOK=200, chưa co repetition_penalty) phat hien
41.7% (70/168) van loi — khong phai thieu token nua ma la MODEL LAP VONG LAP
(greedy decoding de mac ket lap cum tu voi noi dung dang danh sach/liet ke dai).
Da them repetition_penalty=1.3 + no_repeat_ngram_size=3 vao generate() de chan
dung — day la sua GOC, khong phai tang MAX_TOK them nua.

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON
Add Input: dataset keyframe gộp (như 09_ocr_qwen3vl.py) — chỉ cần các shard chứa
video L21/L22/L25/L30 (168 ảnh nằm rải trong 4 shard này).

ĐẦU RA: /kaggle/working/ocr_fix/ocr_fixed.jsonl — chỉ chứa 168 dòng đã sửa.
Tải về rồi ghép đè vào 5 file ocr_<ACCOUNT>.jsonl gốc bằng merge_ocr_fix.py.
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "09c-fix-truncated-ocr v1"
print(f">>> {VERSION}", flush=True)

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"
BATCH = int(os.environ.get("BATCH", "16"))
MAX_TOK = int(os.environ.get("MAX_TOK", "200"))   # rong rai han han 64, khong doan nua
MAX_PIXELS = 384 * 384
MIN_PIXELS = 128 * 128
PROMPT = ("Read and transcribe ALL text visible in this image exactly as written, "
          "preserving Vietnamese diacritics and original casing. List each distinct "
          "piece of text on its own line, in reading order (top to bottom, left to "
          "right). Do NOT describe the image or add any commentary — output ONLY the "
          "transcribed text. If there is no visible text anywhere in the image, "
          "respond with exactly: NO_TEXT")

# 168 key (video, n) da xac dinh CHINH XAC tu du lieu that (len(texts)>=250 ky tu,
# soi tay xac nhan deu bi cat giua chung — xem hoi thoai) — KHONG doan.
TRUNC_KEYS = [('L30_V003', 83), ('L30_V003', 84), ('L30_V014', 17), ('L30_V055', 9), ('L30_V055', 95), ('L30_V055', 96), ('L30_V075', 50), ('L22_V004', 399), ('L22_V009', 123), ('L22_V013', 300), ('L22_V017', 37), ('L22_V019', 322), ('L22_V021', 222), ('L22_V022', 193), ('L22_V022', 194), ('L22_V031', 19), ('L22_V031', 297), ('L21_V002', 250), ('L21_V002', 251), ('L21_V002', 252), ('L21_V002', 253), ('L21_V002', 255), ('L21_V002', 256), ('L21_V002', 257), ('L21_V002', 258), ('L21_V002', 259), ('L21_V002', 409), ('L21_V006', 345), ('L21_V015', 379), ('L21_V016', 372), ('L21_V016', 374), ('L21_V016', 375), ('L21_V016', 376), ('L21_V016', 377), ('L21_V019', 181), ('L21_V021', 241), ('L21_V023', 110), ('L21_V023', 124), ('L21_V024', 428), ('L21_V028', 82), ('L21_V028', 319), ('L25_V001', 106), ('L25_V002', 103), ('L25_V003', 62), ('L25_V003', 100), ('L25_V004', 69), ('L25_V004', 131), ('L25_V005', 132), ('L25_V006', 38), ('L25_V006', 92), ('L25_V007', 73), ('L25_V010', 11), ('L25_V011', 10), ('L25_V012', 9), ('L25_V012', 72), ('L25_V013', 9), ('L25_V014', 10), ('L25_V015', 8), ('L25_V015', 50), ('L25_V016', 11), ('L25_V016', 80), ('L25_V017', 10), ('L25_V018', 62), ('L25_V019', 111), ('L25_V020', 104), ('L25_V021', 80), ('L25_V021', 154), ('L25_V022', 140), ('L25_V023', 96), ('L25_V024', 152), ('L25_V025', 169), ('L25_V026', 7), ('L25_V027', 11), ('L25_V028', 13), ('L25_V028', 75), ('L25_V029', 12), ('L25_V029', 74), ('L25_V030', 9), ('L25_V030', 84), ('L25_V032', 9), ('L25_V032', 52), ('L25_V032', 73), ('L25_V032', 103), ('L25_V033', 86), ('L25_V034', 9), ('L25_V035', 19), ('L25_V035', 98), ('L25_V036', 99), ('L25_V037', 108), ('L25_V038', 61), ('L25_V038', 99), ('L25_V039', 122), ('L25_V039', 182), ('L25_V040', 78), ('L25_V040', 108), ('L25_V041', 91), ('L25_V041', 98), ('L25_V042', 141), ('L25_V044', 8), ('L25_V045', 11), ('L25_V045', 95), ('L25_V046', 18), ('L25_V047', 14), ('L25_V047', 64), ('L25_V047', 75), ('L25_V048', 9), ('L25_V048', 111), ('L25_V050', 9), ('L25_V050', 51), ('L25_V050', 52), ('L25_V050', 71), ('L25_V050', 101), ('L25_V050', 102), ('L25_V051', 12), ('L25_V051', 81), ('L25_V052', 8), ('L25_V053', 101), ('L25_V054', 105), ('L25_V055', 106), ('L25_V056', 66), ('L25_V056', 106), ('L25_V057', 81), ('L25_V057', 148), ('L25_V058', 125), ('L25_V059', 86), ('L25_V060', 119), ('L25_V061', 84), ('L25_V061', 133), ('L25_V062', 72), ('L25_V063', 10), ('L25_V064', 15), ('L25_V064', 83), ('L25_V065', 9), ('L25_V065', 70), ('L25_V066', 8), ('L25_V066', 100), ('L25_V067', 11), ('L25_V067', 91), ('L25_V068', 8), ('L25_V068', 70), ('L25_V069', 19), ('L25_V070', 8), ('L25_V071', 105), ('L25_V072', 105), ('L25_V073', 65), ('L25_V073', 101), ('L25_V074', 174), ('L25_V075', 5), ('L25_V075', 44), ('L25_V075', 96), ('L25_V075', 105), ('L25_V076', 79), ('L25_V076', 132), ('L25_V077', 126), ('L25_V078', 76), ('L25_V078', 116), ('L25_V080', 66), ('L25_V080', 113), ('L25_V081', 11), ('L25_V081', 75), ('L25_V082', 7), ('L25_V083', 10), ('L25_V083', 70), ('L25_V084', 105), ('L25_V085', 9), ('L25_V085', 90), ('L25_V087', 18), ('L25_V088', 7)]
print(f"  --> {len(TRUNC_KEYS)} key can sua lai", flush=True)

WORK = Path("/kaggle/working"); OUT = WORK / "ocr_fix"; OUT.mkdir(parents=True, exist_ok=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. NẠP MODEL ====================
print("=" * 60, "\n[1/3] Nap Qwen3-VL-4B\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' accelerate qwen-vl-utils")
sh(f"{sys.executable} -m pip install -q 'pillow==11.1.0'")

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID, dtype=torch.float16, attn_implementation="sdpa", device_map={"": dev}).eval()
processor = AutoProcessor.from_pretrained(MODEL_ID, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
processor.tokenizer.padding_side = "left"
print("  --> model san sang", flush=True)

_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
KF_ROOT_GLOB, MAP_ROOT_GLOB = "/kaggle/input/**/keyframes", "/kaggle/input/**/maps"
if _tar_files:
    import tarfile
    LOCAL_KF = WORK / "kf_extracted"; LOCAL_KF.mkdir(parents=True, exist_ok=True)
    print(f"  Giai nen {len(_tar_files)} tar (keyframes+maps)...", flush=True)
    for tf in _tar_files:
        with tarfile.open(tf) as t:
            members = [m for m in t.getmembers() if "/keyframes/" in m.name or "/maps/" in m.name]
            t.extractall(LOCAL_KF, members=members)
    KF_ROOT_GLOB, MAP_ROOT_GLOB = f"{LOCAL_KF}/**/keyframes", f"{LOCAL_KF}/**/maps"


# ==================== 2. TÌM ĐƯỜNG DẪN ẢNH ====================
print("=" * 60, "\n[2/3] Tim duong dan anh\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
items = []  # (video, n, path)
for video, n in TRUNC_KEYS:
    img_dir = next((os.path.join(kr, video) for kr in kf_roots
                    if os.path.isdir(os.path.join(kr, video))), None)
    if img_dir is None:
        continue
    p = os.path.join(img_dir, f"{n:06d}.webp")
    if os.path.exists(p):
        items.append((video, n, p))
print(f"  --> tim duoc anh cho {len(items)}/{len(TRUNC_KEYS)} key", flush=True)
if not items:
    raise RuntimeError("0 anh tim thay — kiem tra lai Add Input co du shard L21_a/L22_a/L25_a/L30_a khong.")


# ==================== 3. OCR LẠI (MAX_TOK rộng hơn) ====================
print("=" * 60, "\n[3/3] OCR lai\n", "=" * 60, flush=True)


@torch.no_grad()
def ocr_batch(paths):
    messages = [[{"role": "user", "content": [
        {"type": "image", "image": f"file://{p}", "min_pixels": MIN_PIXELS, "max_pixels": MAX_PIXELS},
        {"type": "text", "text": PROMPT}]}] for p in paths]
    texts_in = [processor.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in messages]
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(text=texts_in, images=image_inputs, padding=True, return_tensors="pt").to(dev)
    gen = model.generate(**inputs, max_new_tokens=MAX_TOK, do_sample=False, use_cache=True,
                          repetition_penalty=1.3, no_repeat_ngram_size=3)
    trimmed = gen[:, inputs.input_ids.shape[1]:]
    outs = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return [o.strip() for o in outs]


OUT_JSONL = OUT / "ocr_fixed.jsonl"
done_keys = set()
if OUT_JSONL.exists():
    for line in open(OUT_JSONL, encoding="utf-8"):
        d = json.loads(line)
        done_keys.add((d["video"], d["n"]))
items = [it for it in items if (it[0], it[1]) not in done_keys]
print(f"  --> {len(items)} anh se OCR lai ({len(done_keys)} da xong tu truoc)", flush=True)

t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    try:
        outs = ocr_batch([c[2] for c in chunk])
    except Exception as ex:
        print(f"  [loi batch {bi}: {ex}] -> fallback tung anh", flush=True)
        outs = []
        for c in chunk:
            try:
                outs.append(ocr_batch([c[2]])[0])
            except Exception:
                outs.append("")
    for (video, n, _), out_text in zip(chunk, outs):
        texts = "" if out_text.strip().upper() == "NO_TEXT" else out_text
        fout.write(json.dumps({"video": video, "n": n, "texts": texts}, ensure_ascii=False) + "\n")
    fout.flush()
    print(f"  {bi+len(chunk)}/{len(items)}", flush=True)
fout.close()

print(f"\n  Xong: {len(items)} anh, {(time.time()-t0)/60:.1f} phut", flush=True)
print("\n>>> XONG. Save Version -> Dataset 'aic-ocr-fix'.", flush=True)
print(">>> Ve may: dung merge_ocr_fix.py de thay the dong cu bang dong moi trong 5 file ocr_<ACCOUNT>.jsonl goc.", flush=True)

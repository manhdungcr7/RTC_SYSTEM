"""
================================================================================
KAGGLE — TEST HIỆU CHỈNH: OCR bằng Qwen3-VL-4B trên ~30 ảnh mẫu
================================================================================
09_ocr_qwen3vl.py chạy thật đo được chỉ ~0.6-0.8 img/s (chậm hơn caption ~1.2-2.0
img/s nhiều) — nghi ngờ: generate() theo BATCH đợi hàng CHẬM NHẤT trong batch mới
dừng, nếu model không dừng sớm (EOS) ở ảnh không chữ thì gần như batch nào cũng
chạy tới sát MAX_TOK=150 thay vì dừng nhanh.

Script này in ra THẬT: text sinh ra cho từng ảnh + số token thật + tốc độ, để biết
chắc trước khi sửa MAX_TOK/prompt rồi chạy lại full account (đỡ tốn GPU-giờ đoán mò).

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON | Add Input: dataset keyframe bất kỳ
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

print(">>> test-ocr-qwen-length v1", flush=True)
N_SAMPLE = int(os.environ.get("N_SAMPLE", "30"))
MAX_TOK = int(os.environ.get("MAX_TOK", "150"))   # doi ngay day de thu truoc/sau
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", str(384 * 384)))
MIN_PIXELS = int(os.environ.get("MIN_PIXELS", str(128 * 128)))
PROMPT = os.environ.get("PROMPT",
    "Read and transcribe ALL text visible in this image exactly as written, "
    "preserving Vietnamese diacritics and original casing. List each distinct "
    "piece of text on its own line, in reading order (top to bottom, left to "
    "right). Do NOT describe the image or add any commentary — output ONLY the "
    "transcribed text. If there is no visible text anywhere in the image, "
    "respond with exactly: NO_TEXT")

sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True)
sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' accelerate qwen-vl-utils")

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

t0 = time.time()
model = AutoModelForImageTextToText.from_pretrained(
    "Qwen/Qwen3-VL-4B-Instruct", dtype=torch.float16, attn_implementation="sdpa",
    device_map={"": dev}).eval()
processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-4B-Instruct",
                                           min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
processor.tokenizer.padding_side = "left"
print(f"  --> nap model xong ({time.time()-t0:.1f}s)", flush=True)

# lay mau anh (uu tien nhieu video khac nhau de da dang canh)
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
            step = 0
            for line in f:
                p = line.strip().split(",")
                if len(p) < 2:
                    continue
                step += 1
                if step % 7 != 0:   # rai deu ra thay vi lay lien tiep dau video
                    continue
                ip = os.path.join(img_dir, f"{int(p[0]):06d}.webp")
                if os.path.exists(ip):
                    paths.append(ip)
        if len(paths) >= N_SAMPLE:
            break
    if len(paths) >= N_SAMPLE:
        break
paths = paths[:N_SAMPLE]
print(f"  --> lay {len(paths)} anh mau (rai deu nhieu video)", flush=True)


@torch.no_grad()
def run_one(p):
    messages = [{"role": "user", "content": [
        {"type": "image", "image": f"file://{p}", "min_pixels": MIN_PIXELS, "max_pixels": MAX_PIXELS},
        {"type": "text", "text": PROMPT}]}]
    text_in = processor.apply_chat_template([messages], tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info([messages])
    inputs = processor(text=text_in, images=image_inputs, padding=True, return_tensors="pt").to(dev)
    t0 = time.time()
    gen = model.generate(**inputs, max_new_tokens=MAX_TOK, do_sample=False, use_cache=True)
    dt = time.time() - t0
    trimmed = gen[:, inputs.input_ids.shape[1]:]
    n_tok = trimmed.shape[1]
    hit_cap = int(n_tok >= MAX_TOK)
    out = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()
    return out, n_tok, hit_cap, dt


print("\n" + "=" * 70, f"\nCHAY TUNG ANH 1 (MAX_TOK={MAX_TOK}) — de do CHINH XAC so token that\n", "=" * 70, flush=True)
lens, hits, times = [], 0, []
for i, p in enumerate(paths):
    out, n_tok, hit_cap, dt = run_one(p)
    lens.append(n_tok); hits += hit_cap; times.append(dt)
    flag = "  <<< CHAM TRAN MAX_TOK -- co the bi CAT!" if hit_cap else ""
    print(f"[{i}] {Path(p).name} | {n_tok} token | {dt:.2f}s{flag}", flush=True)
    print(f"     -> {out[:200]!r}", flush=True)

lens_sorted = sorted(lens)
p50 = lens_sorted[len(lens_sorted)//2]
p90 = lens_sorted[int(len(lens_sorted)*0.9)]
print("\n" + "=" * 70, flush=True)
print(f"TOM TAT ({len(paths)} anh, MAX_TOK={MAX_TOK}):", flush=True)
print(f"  so token sinh ra: median={p50} | p90={p90} | max={max(lens)} | min={min(lens)}", flush=True)
print(f"  so anh CHAM TRAN MAX_TOK (nghi bi cat): {hits}/{len(paths)}", flush=True)
print(f"  thoi gian trung binh/anh (chay DON, khong batch): {sum(times)/len(times):.2f}s", flush=True)
print(">>> XONG. Doc ky cot 'texts' — neu nhieu anh KHONG CO CHU van sinh dai/lap ->", flush=True)
print("    prompt chua ep model dung dung; neu p90 << MAX_TOK -> ha MAX_TOK an toan de nhanh hon.", flush=True)

"""
================================================================================
KAGGLE — TEST NHANH: caption thật cần bao nhiêu token? (chạy TRƯỚC khi sửa MAX_TOK)
================================================================================
Chạy ~30 ảnh với max_new_tokens=200 (RỘNG RÃI, chắc chắn không cắt) rồi đo THẬT số
token mỗi câu dùng (tính tới EOS, không tính phần đệm) — từ đó biết chính xác nên
đặt MAX_TOK bao nhiêu trong 07_caption_qwen3vl.py, thay vì đoán.

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON | Add Input: bất kỳ dataset keyframe nào
(VD aic-kf-batch1-all) — chỉ cần vài chục ảnh mẫu, không quan trọng shard nào.
Dùng 1 account RẢNH (4 hoặc 5) — không đụng tới account 1/2/3 đang caption.
================================================================================
"""
import os, sys, json, glob, subprocess
from pathlib import Path

print(">>> test-caption-length v1", flush=True)

N_SAMPLE = int(os.environ.get("N_SAMPLE", "30"))
MAX_TOK_TEST = int(os.environ.get("MAX_TOK_TEST", "200"))   # rong rai, khong cat
MAX_PIXELS = 384 * 384
MIN_PIXELS = 128 * 128
PROMPT = ("Describe this image in one detailed sentence: the people and their actions, "
          "the setting, key objects and colors, and any visible on-screen text or graphics.")

sh = lambda c: subprocess.run(c, shell=True, capture_output=True, text=True)
sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' accelerate qwen-vl-utils")
sh(f"{sys.executable} -m pip install -q 'pillow==11.1.0'")

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

model = AutoModelForImageTextToText.from_pretrained(
    "Qwen/Qwen3-VL-4B-Instruct", dtype=torch.float16, attn_implementation="sdpa",
    device_map={"": dev}).eval()
processor = AutoProcessor.from_pretrained("Qwen/Qwen3-VL-4B-Instruct",
                                           min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
processor.tokenizer.padding_side = "left"
print("  --> model san sang", flush=True)

# giai nen tar dau tien tim thay (chi lay mau, khong can toan bo)
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
        if len(paths) >= N_SAMPLE:
            break
    if len(paths) >= N_SAMPLE:
        break
paths = paths[:N_SAMPLE]
print(f"  --> lay mau {len(paths)} anh", flush=True)

messages = [[{"role": "user", "content": [
    {"type": "image", "image": f"file://{p}", "min_pixels": MIN_PIXELS, "max_pixels": MAX_PIXELS},
    {"type": "text", "text": PROMPT}]}] for p in paths]
texts = [processor.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in messages]
image_inputs, _ = process_vision_info(messages)
inputs = processor(text=texts, images=image_inputs, padding=True, return_tensors="pt").to(dev)

with torch.no_grad():
    gen = model.generate(**inputs, max_new_tokens=MAX_TOK_TEST, do_sample=False, use_cache=True)
trimmed = gen[:, inputs.input_ids.shape[1]:]

eos_id = processor.tokenizer.eos_token_id
lens, truncated = [], 0
print("\n" + "=" * 70, flush=True)
for i, row in enumerate(trimmed):
    row_list = row.tolist()
    if eos_id in row_list:
        real_len = row_list.index(eos_id)          # so token THAT truoc EOS
    else:
        real_len = len(row_list); truncated += 1    # KHONG co EOS trong 200 token -> qua dai that
    lens.append(real_len)
    cap = processor.tokenizer.decode(row[:real_len], skip_special_tokens=True).strip()
    print(f"[{i}] {real_len} token | {cap}", flush=True)

lens.sort()
print("\n" + "=" * 70, flush=True)
print(f"THONG KE (n={len(lens)}):", flush=True)
print(f"  min={lens[0]}  max={lens[-1]}  median={lens[len(lens)//2]}  "
      f"trung binh={sum(lens)/len(lens):.1f}", flush=True)
print(f"  90th percentile ~ {lens[int(len(lens)*0.9)]}", flush=True)
print(f"  so cau VAN CON DAI (khong co EOS trong {MAX_TOK_TEST} token, tuc qua dai that): {truncated}", flush=True)
print(f"\n  --> DE XUAT MAX_TOK = 90th percentile + bien an toan (~10-15 token)", flush=True)
print(">>> XONG.", flush=True)

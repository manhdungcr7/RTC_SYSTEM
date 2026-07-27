"""
================================================================================
KAGGLE — SỬA caption bị cắt cụt (MAX_TOK=128 không đủ cho ~5% ảnh phức tạp nhất)
================================================================================
Đọc TẤT CẢ captions_*.jsonl đã có, tìm những dòng KHÔNG kết thúc bằng dấu câu rõ
ràng (dấu hiệu bị cắt giữa chừng — đã đo: ~5%, 9,108/182,422), rồi CHỈ chạy lại
caption cho đúng những ảnh đó với max_new_tokens=200 (rộng rãi hơn nhiều).

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON
Add Input: dataset keyframe gộp (aic-kf-batch1-all) + upload 5 file captions_*.jsonl
cũ làm 1 dataset input (VD "aic-captions-v1") để script đọc và tìm dòng cần sửa.

ĐẦU RA: /kaggle/working/captions_fixed.jsonl — CHỈ chứa các dòng đã sửa (video,n,
frame_idx,cap mới). Sau khi tải về, ghép đè vào 5 file gốc bằng script gộp riêng
(xem hướng dẫn cuối file).
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "07c-fix-truncated-captions v1"
print(f">>> {VERSION}", flush=True)

MODEL_ID = "Qwen/Qwen3-VL-4B-Instruct"
BATCH = int(os.environ.get("BATCH", "16"))
MAX_TOK = int(os.environ.get("MAX_TOK", "200"))   # rong rai han, khong doan nua
MAX_PIXELS = 384 * 384
MIN_PIXELS = 128 * 128
PROMPT = ("Describe this image in one detailed sentence: the people and their actions, "
          "the setting, key objects and colors, and any visible on-screen text or graphics.")

# CHIA ACCOUNT (tuy chon): dat SPLIT="1/3" de account nay chi lam 1/3 dau danh sach loi,
# SPLIT="2/3", "3/3" cho 2 account con lai. De trong = lam het.
SPLIT = os.environ.get("SPLIT", "")

WORK = Path("/kaggle/working"); OUT = WORK / "fix"; OUT.mkdir(parents=True, exist_ok=True)


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. TIM CAC DONG BI CAT CUT ====================
print("=" * 60, "\n[1/4] Tim caption bi cat cut trong cac file .jsonl da co\n", "=" * 60, flush=True)
old_caption_files = glob.glob("/kaggle/input/**/captions_*.jsonl", recursive=True)
print(f"  Tim thay {len(old_caption_files)} file captions cu: {old_caption_files}", flush=True)

END_OK = (".", "!", "?", '"', "”")
broken = []   # (video, n, frame_idx)
for fp in old_caption_files:
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            cap = d["cap"].strip()
            if not cap.endswith(END_OK):
                broken.append((d["video"], d["n"], d["frame_idx"]))

print(f"  --> {len(broken):,} caption bi cat cut can sua", flush=True)

if SPLIT:
    idx, total = map(int, SPLIT.split("/"))
    chunk = len(broken) // total + 1
    broken = broken[(idx - 1) * chunk: idx * chunk]
    print(f"  SPLIT={SPLIT} -> account nay xu ly {len(broken):,} anh", flush=True)

if not broken:
    print(">>> Khong co gi de sua. XONG.", flush=True)
    sys.exit(0)

broken_keys = {(v, n) for v, n, _ in broken}


# ==================== 2. NAP MODEL ====================
print("=" * 60, "\n[2/4] Nap Qwen3-VL-4B\n", "=" * 60, flush=True)
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

# giai nen keyframes+maps tu tar (neu dataset la ban gop)
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


# ==================== 3. TIM DUONG DAN ANH CHO CAC KEY CAN SUA ====================
print("=" * 60, "\n[3/4] Tim duong dan anh\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
items = []  # (video, n, frame_idx, path)
for video, n, frame_idx in broken:
    img_dir = next((os.path.join(kr, video) for kr in kf_roots
                    if os.path.isdir(os.path.join(kr, video))), None)
    if img_dir is None:
        continue
    p = os.path.join(img_dir, f"{n:06d}.webp")
    if os.path.exists(p):
        items.append((video, n, frame_idx, p))
print(f"  --> tim duoc anh cho {len(items):,}/{len(broken):,} muc can sua", flush=True)


# ==================== 4. CAPTION LAI (max_tok rong hon) ====================
print("=" * 60, "\n[4/4] Caption lai\n", "=" * 60, flush=True)


@torch.no_grad()
def caption_batch(paths):
    messages = [[{"role": "user", "content": [
        {"type": "image", "image": f"file://{p}", "min_pixels": MIN_PIXELS, "max_pixels": MAX_PIXELS},
        {"type": "text", "text": PROMPT}]}] for p in paths]
    texts = [processor.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in messages]
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(text=texts, images=image_inputs, padding=True, return_tensors="pt").to(dev)
    gen = model.generate(**inputs, max_new_tokens=MAX_TOK, do_sample=False, use_cache=True)
    trimmed = gen[:, inputs.input_ids.shape[1]:]
    caps = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return [c.strip().replace("\n", " ") for c in caps]


OUT_JSONL = OUT / "captions_fixed.jsonl"
done_keys = set()
if OUT_JSONL.exists():
    for line in open(OUT_JSONL, encoding="utf-8"):
        d = json.loads(line)
        done_keys.add((d["video"], d["n"]))
items = [it for it in items if (it[0], it[1]) not in done_keys]
print(f"  --> {len(items):,} anh se caption lai ({len(done_keys):,} da xong tu truoc)", flush=True)

t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
still_broken = 0
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    try:
        caps = caption_batch([c[3] for c in chunk])
    except Exception as ex:
        print(f"  [loi batch {bi}: {ex}] -> fallback tung anh", flush=True)
        caps = []
        for c in chunk:
            try:
                caps.append(caption_batch([c[3]])[0])
            except Exception:
                caps.append("")
    for (video, n, frame_idx, _), cap in zip(chunk, caps):
        if not cap.strip().endswith(END_OK):
            still_broken += 1
        fout.write(json.dumps({"video": video, "n": n, "frame_idx": frame_idx, "cap": cap},
                              ensure_ascii=False) + "\n")
    fout.flush()
    done = bi + len(chunk)
    if (bi // BATCH) % 20 == 0:
        r = done / (time.time() - t0)
        print(f"  {done:,}/{len(items):,} | {r:.1f} img/s | con van cat cut: {still_broken}", flush=True)
fout.close()

print(f"\n  Xong: {done if items else 0} anh, {(time.time()-t0)/60:.1f} phut, "
      f"van con cat cut du 200 token: {still_broken}", flush=True)
print("\n>>> XONG. Save Version -> Dataset 'aic-caption-fix-<so>'.", flush=True)
print(">>> Ve may: dung script gop de thay the dong cu bang dong moi trong 5 file captions_*.jsonl goc.", flush=True)

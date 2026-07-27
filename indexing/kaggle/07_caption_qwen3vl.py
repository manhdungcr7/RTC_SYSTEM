"""
================================================================================
KAGGLE NOTEBOOK 07 — CAPTION (Qwen3-VL-4B-Instruct) cho TOÀN BỘ keyframe
================================================================================
Sinh caption tiếng Anh cô đọng cho MỌI keyframe (182,422) → tín hiệu text-to-caption
(t2c) bổ sung cho retrieval (bắt được câu query mô tả "chủ đề/hành động" mà visual
thuần đôi khi trượt). Qwen3-VL-4B: OCRBench 88.1 > Qwen2.5-VL-7B 86.4, nhẹ hơn ~40%,
throughput ~1.4-1.6x — thế hệ mới, đa phương thức từ gốc.

CẤU HÌNH KAGGLE:
  - Accelerator : GPU T4 x2 (script dùng cuda:0 — 1 GPU/notebook cho ổn định)
  - Internet    : ON (cài transformers/qwen-vl-utils + tải model lần đầu ~9GB)
  - Add Input   : dataset keyframe gộp từ notebook 01 (VD aic-kf-batch1-all)

CHIA 5 ACCOUNT (cân bằng theo SỐ KEYFRAME THẬT — đọc từ shard_info.json/account_summary.json
đã tải về, không phải ước lượng — để cả 5 account xong gần cùng lúc):
  ACCOUNT = "1"  -> 35,363 kf   (L22_a, L29_a, L25_a1)
  ACCOUNT = "2"  -> 36,027 kf   (L26_c, L28_a, L30_a)
  ACCOUNT = "3"  -> 37,075 kf   (L26_d, L21_a, L24_a)
  ACCOUNT = "4"  -> 36,287 kf   (L26_e, L26_a, L25_b)
  ACCOUNT = "5"  -> 37,670 kf   (L26_b, L25_a, L27_a, L23_a)

TỐI ƯU TỐC ĐỘ (đã áp dụng):
  1. BATCH inference (padding_side='left') — sinh nhiều ảnh 1 lượt, KHÔNG 1-cái-1.
  2. GIỚI HẠN độ phân giải ảnh (max_pixels) — Qwen-VL dùng dynamic resolution, ảnh to
     = nhiều vision token = CHẬM. Keyframe đã là thumbnail 384px → cap chặt cho nhanh.
  3. Prompt CÔ ĐỌNG + max_new_tokens=128 — đo THẬT trên 30 ảnh mẫu (07b_test_caption_length.py):
     median=73, p90=100 token cho câu đủ ý (không cắt) → 128 đủ margin an toàn.
  4. attn_implementation='sdpa' (FlashAttention-2 KHÔNG chạy trên T4 sm_7.5).
  5. RESUMABLE — ghi tăng dần vào .jsonl, chạy lại tự bỏ qua keyframe đã caption
     (session Kaggle 12h có thể không đủ 1 lần → cứ chạy lại notebook là tiếp tục).

ĐẦU RA (/kaggle/working/caption → Save Version → Dataset "aic-caption-<ACCOUNT>"):
  captions_<ACCOUNT>.jsonl   mỗi dòng: {"video","n","frame_idx","cap"}
================================================================================
"""
import os, sys, json, time, glob, subprocess
from pathlib import Path

VERSION = "07-caption-qwen3vl v1"
print(f">>> {VERSION}", flush=True)

# ============================ CẤU HÌNH ============================
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-VL-4B-Instruct")
BATCH    = int(os.environ.get("BATCH", "8"))
MAX_TOK  = int(os.environ.get("MAX_TOK", "128"))  # do THAT tren 30 anh mau: median=73,
                                                    # p90=100 token -> 64 cu CAT CUT hon nua so caption
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", str(384 * 384)))   # cap vision token → nhanh
MIN_PIXELS = int(os.environ.get("MIN_PIXELS", str(128 * 128)))
PROMPT = os.environ.get("PROMPT",
    "Describe this image in one detailed sentence: the people and their actions, "
    "the setting, key objects and colors, and any visible on-screen text or graphics.")

# CHIA 5 ACCOUNT — cân bằng theo số keyframe THẬT (xem docstring)
ACCOUNT_GROUPS = {
    "1": ["L22_a", "L29_a", "L25_a1"],
    "2": ["L26_c", "L28_a", "L30_a"],
    "3": ["L26_d", "L21_a", "L24_a"],
    "4": ["L26_e", "L26_a", "L25_b"],
    "5": ["L26_b", "L25_a", "L27_a", "L23_a"],
}
ACCOUNT = os.environ.get("ACCOUNT", "1")   # <<< SỬA Ở ĐÂY: "1" / "2" / "3"
if ACCOUNT in ACCOUNT_GROUPS:
    SHARDS = ACCOUNT_GROUPS[ACCOUNT]
elif ACCOUNT.strip():
    SHARDS = [s.strip() for s in ACCOUNT.split(",") if s.strip()]   # thủ công / batch 2
else:
    SHARDS = []   # rỗng = chạy hết
print(f"  ACCOUNT={ACCOUNT!r} --> {len(SHARDS)} shard: {SHARDS}", flush=True)

WORK = Path("/kaggle/working"); OUT = WORK / "caption"; OUT.mkdir(parents=True, exist_ok=True)
OUT_JSONL = OUT / f"captions_{ACCOUNT}.jsonl"


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. CÀI ĐẶT + NẠP MODEL ====================
print("=" * 60, "\n[1/4] Cai dat + nap Qwen3-VL-4B\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57' accelerate qwen-vl-utils pyarrow pandas")
sh(f"{sys.executable} -m pip install -q 'pillow==11.1.0'")   # tránh lỗi Pillow bleeding-edge (như 02)

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor
from qwen_vl_utils import process_vision_info

dev = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"  GPU: {torch.cuda.get_device_name(0) if dev.startswith('cuda') else 'KHONG CO GPU!'}", flush=True)

# T4 (sm_7.5) chi ho tro FP16 (khong bf16). Qwen train bf16 → fp16 co the tran so hiem gap.
# Neu gap crash 'device-side assert' lap lai → doi DTYPE sang bfloat16 (T4 chay duoc nhung cham hon).
DTYPE = torch.float16 if os.environ.get("DTYPE", "fp16") == "fp16" else torch.bfloat16

t0 = time.time()
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID, dtype=DTYPE, attn_implementation="sdpa", device_map={"": dev}).eval()
processor = AutoProcessor.from_pretrained(MODEL_ID, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
processor.tokenizer.padding_side = "left"   # BẮT BUỘC cho batch generate (cắt output đồng đều)
print(f"  --> nap xong {MODEL_ID} ({time.time()-t0:.1f}s) | dtype={DTYPE}", flush=True)

# giai nen keyframes+maps tu tar (chi cac shard cua account nay) — KHONG can audio
_tar_files = glob.glob("/kaggle/input/**/archives/*.tar", recursive=True)
if SHARDS:
    _tar_files = [tf for tf in _tar_files if Path(tf).stem in SHARDS]
KF_ROOT_GLOB = "/kaggle/input/**/keyframes"
MAP_ROOT_GLOB = "/kaggle/input/**/maps"
if _tar_files:
    import tarfile
    LOCAL_KF = WORK / "kf_extracted"; LOCAL_KF.mkdir(parents=True, exist_ok=True)
    print(f"  Giai nen {len(_tar_files)} tar (keyframes+maps)...", flush=True)
    for i, tf in enumerate(_tar_files):
        te = time.time()
        with tarfile.open(tf) as t:
            members = [m for m in t.getmembers()
                       if "/keyframes/" in m.name or "/maps/" in m.name]
            t.extractall(LOCAL_KF, members=members)
        print(f"  [{i+1}/{len(_tar_files)}] {Path(tf).name} ({time.time()-te:.1f}s)", flush=True)
    KF_ROOT_GLOB = f"{LOCAL_KF}/**/keyframes"
    MAP_ROOT_GLOB = f"{LOCAL_KF}/**/maps"


# ==================== 2. GOM DANH SÁCH KEYFRAME (loc theo shard) ====================
print("=" * 60, "\n[2/4] Gom danh sach keyframe\n", "=" * 60, flush=True)
kf_roots = glob.glob(KF_ROOT_GLOB, recursive=True)
map_roots = glob.glob(MAP_ROOT_GLOB, recursive=True)
if SHARDS:
    kf_roots  = [k for k in kf_roots if Path(k).parent.name in SHARDS]
    map_roots = [m for m in map_roots if Path(m).parent.name in SHARDS]
if not kf_roots:
    raise FileNotFoundError("Khong thay 'keyframes' — nho Add dataset tu notebook 01 + dung ACCOUNT.")

items = []   # (video, n, frame_idx, img_path)
for mroot in map_roots:
    for csv in sorted(glob.glob(os.path.join(mroot, "*.csv"))):
        video = Path(csv).stem
        img_dir = None
        for kr in kf_roots:
            d = os.path.join(kr, video)
            if os.path.isdir(d):
                img_dir = d; break
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

# RESUMABLE: bo qua keyframe da caption o lan chay truoc
done = set()
if OUT_JSONL.exists():
    for line in open(OUT_JSONL, encoding="utf-8"):
        try:
            d = json.loads(line)
            done.add((d["video"], d["n"]))
        except Exception:
            pass
items = [it for it in items if (it[0], it[1]) not in done]
print(f"  --> {len(items):,} keyframe se caption ({len(done):,} da xong tu truoc)", flush=True)
if not items:
    print(">>> KHONG con keyframe nao — da xong het.", flush=True)
    sys.exit(0)


# ==================== 3. CAPTION THEO BATCH ====================
print("=" * 60, "\n[3/4] Caption (batch)\n", "=" * 60, flush=True)


@torch.no_grad()
def caption_batch(paths):
    messages = [[{"role": "user", "content": [
        {"type": "image", "image": f"file://{p}", "min_pixels": MIN_PIXELS, "max_pixels": MAX_PIXELS},
        {"type": "text", "text": PROMPT}]}] for p in paths]
    texts = [processor.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in messages]
    image_inputs, _ = process_vision_info(messages)
    inputs = processor(text=texts, images=image_inputs, padding=True, return_tensors="pt").to(dev)
    gen = model.generate(**inputs, max_new_tokens=MAX_TOK, do_sample=False, use_cache=True)
    trimmed = gen[:, inputs.input_ids.shape[1]:]   # padding_side=left → cat dong deu
    caps = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return [c.strip().replace("\n", " ") for c in caps]


t0 = time.time()
fout = open(OUT_JSONL, "a", encoding="utf-8")
n_done = 0
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    try:
        caps = caption_batch([c[3] for c in chunk])
    except Exception as ex:
        # batch loi (anh hong / OOM) → thu tung anh 1 de khong mat ca batch
        print(f"  [batch {bi} loi: {type(ex).__name__} {str(ex)[:80]}] -> fallback tung anh", flush=True)
        caps = []
        for c in chunk:
            try:
                caps.append(caption_batch([c[3]])[0])
            except Exception:
                caps.append("")
    for (video, n, frame_idx, _), cap in zip(chunk, caps):
        fout.write(json.dumps({"video": video, "n": n, "frame_idx": frame_idx, "cap": cap},
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
print(f"  captions_{ACCOUNT}.jsonl: {total:,} dong | {(time.time()-t0)/60:.1f} phut lan nay", flush=True)
print(f">>> XONG. Save Version -> Dataset 'aic-caption-{ACCOUNT}'.", flush=True)
print(">>> Neu chua het (session het gio): chay lai notebook — tu bo qua phan da xong.", flush=True)

"""
================================================================================
KAGGLE NOTEBOOK 10 — CAP_EMB: vector hoá câu caption (Qwen3-Embedding-4B)
================================================================================
Vector hoá 167,850 câu caption (đã dedup L25_a1/L25_b) bằng Qwen3-Embedding-4B —
KHÔNG dùng MetaCLIP-2 nữa (text-tower CLIP không hợp cho text-to-text retrieval,
xem thảo luận). Chọn Qwen3-Embedding theo bằng chứng THẬT trên benchmark tiếng
Việt VN-MTEB (EACL 2026, arXiv:2507.21500) — họ Qwen (gte-Qwen2-7B/1.5B-instruct)
đứng đầu cột Retrieval (46.05 / 42.01), vượt BGE-M3 (39.84) và cả model chuyên
tiếng Việt Vietnamese-Embedding (34.18). Qwen3-Embedding-4B là thế hệ kế thừa
cùng hệ, cỡ vừa phải (không cần bản 7B nặng hơn mà điểm chỉ nhỉnh ~4 điểm).

Dùng sentence-transformers (cách chính thức Qwen khuyến nghị) — tự xử lý đúng
last-token pooling, tránh lỗi API tự đoán (đã gặp với MetaCLIP-2: 'text_embeds'
không tồn tại trong output AutoModel thường).

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON
Add Input: dataset chứa captions_all.jsonl (đã dedup xong, ~30MB)

ĐẦU RA (/kaggle/working/cap_emb → Save Version → Dataset "aic-cap-emb"):
  feat_capemb.npy       (N, D) float32 — vector CAPTION, đã L2-normalize (encode
                         mặc định của sentence-transformers cho model nay)
  feat_index.parquet    N dòng: video, n
  cap_emb_info.json
================================================================================
"""
import os, sys, json, time, glob
from pathlib import Path
import numpy as np

VERSION = "10-cap-embed v2 (Qwen3-Embedding-4B)"
print(f">>> {VERSION}", flush=True)

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-Embedding-4B")
TAG = "capemb"
BATCH = int(os.environ.get("BATCH", "32"))   # encode = 1 forward pass/cau (KHONG autoregressive
                                              # nhu caption/OCR) -> nhanh hon nhieu, co the tang neu
                                              # khong OOM (xem log toc do ~batch dau de quyet dinh)

WORK = Path("/kaggle/working"); OUT = WORK / "cap_emb"; OUT.mkdir(parents=True, exist_ok=True)

import subprocess


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. GOM CAPTION (DEDUP L25_a1/L25_b) ====================
print("=" * 60, "\n[1/4] Doc captions_*.jsonl, dedup theo (video,n)\n", "=" * 60, flush=True)
cap_files = sorted(glob.glob("/kaggle/input/**/captions_*.jsonl", recursive=True))
print(f"  tim thay {len(cap_files)} file: {cap_files}", flush=True)
if not cap_files:
    raise FileNotFoundError("Khong thay captions_*.jsonl trong /kaggle/input — nho Add dataset caption.")

items = []  # (video, n, cap)
seen = set()
n_dup = 0
for fp in cap_files:
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            key = (d["video"], d["n"])
            if key in seen:
                n_dup += 1
                continue
            seen.add(key)
            items.append((d["video"], d["n"], d["cap"]))
print(f"  --> {len(items):,} caption sau dedup (bo {n_dup:,} dong trung L25_a1/L25_b)", flush=True)


# ==================== 2. NẠP Qwen3-Embedding-4B ====================
print("=" * 60, "\n[2/4] Nap Qwen3-Embedding-4B\n", "=" * 60, flush=True)
sh(f"{sys.executable} -m pip install -q -U 'sentence-transformers>=3.0' 'transformers>=4.51'")

import torch
from sentence_transformers import SentenceTransformer

dev = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(MODEL_ID, device=dev,
                             model_kwargs={"dtype": torch.float16, "attn_implementation": "sdpa"},
                             tokenizer_kwargs={"padding_side": "left"})
print(f"  model tren {dev} | {torch.cuda.get_device_name(0) if dev=='cuda' else ''} | "
      f"dim={model.get_sentence_embedding_dimension()}", flush=True)


# ==================== 3. ENCODE ====================
print("=" * 60, "\n[3/4] Encode caption\n", "=" * 60, flush=True)
# LUU Y: caption la phia "document" (khong can prompt/instruction). Luc query
# thuc te sau nay (core/search.py), cau query se encode voi prompt_name="query"
# (template rieng cua Qwen3-Embedding cho phia truy van) — khac ben nay.
out_arr = None
t0 = time.time()
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    texts = [c[2] for c in chunk]
    v = model.encode(texts, batch_size=len(texts), normalize_embeddings=True,
                      show_progress_bar=False, convert_to_numpy=True)
    if out_arr is None:
        out_arr = np.zeros((len(items), v.shape[1]), dtype=np.float16)
    out_arr[bi:bi + len(v)] = v.astype(np.float16)
    if (bi // BATCH) % 20 == 0:
        done = bi + len(v)
        r = done / (time.time() - t0)
        print(f"  {done:,}/{len(items):,} | {r:.1f} cap/s | con ~{(len(items)-done)/r/60:.1f} phut", flush=True)

np.save(OUT / f"feat_{TAG}.npy", out_arr)


# ==================== 4. LƯU INDEX + INFO ====================
print("=" * 60, "\n[4/4] Luu index + info\n", "=" * 60, flush=True)
import pandas as pd
df = pd.DataFrame([(v, n) for (v, n, _) in items], columns=["video", "n"])
df.to_parquet(OUT / "feat_index.parquet")
info = {"model": MODEL_ID, "tag": TAG, "n": len(items), "dim": int(out_arr.shape[1]),
        "dtype": "float16", "minutes": round((time.time() - t0) / 60, 1)}
json.dump(info, open(OUT / "cap_emb_info.json", "w"), indent=2)
mb = (OUT / f"feat_{TAG}.npy").stat().st_size / 1e6
print(f"  feat_{TAG}.npy: {out_arr.shape} ({mb:.0f} MB) | {info['minutes']} phut", flush=True)
print("\n>>> XONG. Save Version -> Dataset 'aic-cap-emb'.", flush=True)

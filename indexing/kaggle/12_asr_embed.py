"""
================================================================================
KAGGLE NOTEBOOK 12 — ASR_EMB: vector hoá đoạn ASR (Qwen3-Embedding-4B)
================================================================================
Vector hoá 111,411 đoạn ASR (đã dedup video trùng L25_a1/L25_b) bằng Qwen3-
Embedding-4B — CÙNG MODEL, CÙNG QUY TẮC PHÍA DOCUMENT (không prompt_name) như
10_cap_embed.py, để search NGỮ NGHĨA (semantic) thay vì chỉ khớp từ (Meilisearch
BM25-ish hiện tại — xem core/repositories/meili_repo.py::search_asr). Ví dụ câu
hỏi "giá xăng tăng" sẽ khớp được đoạn ASR nói "giá nhiên liệu leo thang" dù
không chung từ nào — điều Meilisearch không làm được.

QUAN TRỌNG — KHÁC 11_encode_service.py: notebook đó (chạy thường trực, phục vụ
query-time) encode capemb với prompt_name="query" (đúng cho PHÍA TRUY VẤN theo
tài liệu Qwen3-Embedding). Notebook NÀY encode PHÍA DOCUMENT (không prompt) —
encode lẫn 2 phía sẽ ra vector KHÔNG tương thích, âm thầm cho kết quả sai chứ
không lỗi. ĐỪNG dùng notebook 11 cho việc này.

CẤU HÌNH KAGGLE: GPU T4 x2 | Internet ON
Add Input: dataset chứa asr_1/asr_all.jsonl, asr_2/asr_all.jsonl, asr_3/asr_all.jsonl
           (hoặc gộp chung 1 thư mục — script tự glob **/asr_all.jsonl, dùng tên
           thư mục cha để biết đoạn đó thuộc file nào nếu cần debug)

ĐẦU RA (/kaggle/working/asr_emb → Save Version → Dataset "aic-asr-emb"):
  feat_asremb.npy       (N, 2560) float16 — vector ASR, đã L2-normalize
  feat_index.parquet    N dòng: video, seg_idx, start, end
  asr_emb_info.json

SAU KHI TẢI VỀ: đặt vào aic-system/artifacts/asr_emb/, chạy lại
  python aic-system/indexing/build_faiss.py
để build nhánh FAISS "asr_emb" (script tự phát hiện, không cần sửa gì thêm).
================================================================================
"""
import os, sys, json, time, glob
from pathlib import Path
import numpy as np

VERSION = "12-asr-embed v1 (Qwen3-Embedding-4B, document side)"
print(f">>> {VERSION}", flush=True)

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-Embedding-4B")
TAG = "asremb"
BATCH = int(os.environ.get("BATCH", "32"))

WORK = Path("/kaggle/working"); OUT = WORK / "asr_emb"; OUT.mkdir(parents=True, exist_ok=True)

import subprocess


def sh(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
        raise RuntimeError(cmd)
    return r


# ==================== 1. GOM ĐOẠN ASR (DEDUP VIDEO TRÙNG L25_a1/L25_b) ====================
print("=" * 60, "\n[1/4] Doc asr_all.jsonl, dedup theo VIDEO (giu ban dau tien)\n", "=" * 60, flush=True)
asr_files = sorted(glob.glob("/kaggle/input/**/asr_all.jsonl", recursive=True))
print(f"  tim thay {len(asr_files)} file: {asr_files}", flush=True)
if not asr_files:
    raise FileNotFoundError("Khong thay asr_all.jsonl trong /kaggle/input — nho Add dataset ASR.")

# GIONG HET indexing/build_meili.py::build_asr() -> dedup PHAI khop 1:1 voi ban
# Meilisearch dang dung, khong thi 2 nguon lech nhau ve tap video.
seen_videos = set()
items = []  # (video, seg_idx, start, end, text)
n_dup = 0
for fp in asr_files:
    with open(fp, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            video = d["video"]
            if video in seen_videos:
                n_dup += 1
                continue
            seen_videos.add(video)
            for seg_idx, seg in enumerate(d.get("segments", [])):
                items.append((video, seg_idx, seg["s"], seg["e"], seg["t"]))
print(f"  --> {len(seen_videos):,} video ASR (bo {n_dup} video trung L25_a1/L25_b), "
      f"{len(items):,} doan ASR", flush=True)


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
print("=" * 60, "\n[3/4] Encode doan ASR\n", "=" * 60, flush=True)
# LUU Y: doan ASR la phia "document" (khong prompt/instruction) — GIONG cap_emb,
# KHAC luc query (core/query_encoders.py dung prompt_name="query"). Dung sai phia
# se khong loi nhung ket qua sai (2 khong gian vector khong tuong thich hoan toan
# du cung model, vi Qwen3-Embedding encode template khac nhau 2 phia).
out_arr = None
t0 = time.time()
for bi in range(0, len(items), BATCH):
    chunk = items[bi:bi + BATCH]
    texts = [c[4] for c in chunk]
    v = model.encode(texts, batch_size=len(texts), normalize_embeddings=True,
                      show_progress_bar=False, convert_to_numpy=True)
    if out_arr is None:
        out_arr = np.zeros((len(items), v.shape[1]), dtype=np.float16)
    out_arr[bi:bi + len(v)] = v.astype(np.float16)
    if (bi // BATCH) % 20 == 0:
        done = bi + len(v)
        r = done / (time.time() - t0)
        print(f"  {done:,}/{len(items):,} | {r:.1f} doan/s | con ~{(len(items)-done)/r/60:.1f} phut", flush=True)

np.save(OUT / f"feat_{TAG}.npy", out_arr)


# ==================== 4. LƯU INDEX + INFO ====================
print("=" * 60, "\n[4/4] Luu index + info\n", "=" * 60, flush=True)
import pandas as pd
df = pd.DataFrame([(v, si, s, e) for (v, si, s, e, _) in items],
                   columns=["video", "seg_idx", "start", "end"])
df.to_parquet(OUT / "feat_index.parquet")
info = {"model": MODEL_ID, "tag": TAG, "n": len(items), "dim": int(out_arr.shape[1]),
        "dtype": "float16", "minutes": round((time.time() - t0) / 60, 1)}
json.dump(info, open(OUT / f"{TAG}_info.json", "w"), indent=2)
mb = (OUT / f"feat_{TAG}.npy").stat().st_size / 1e6
print(f"  feat_{TAG}.npy: {out_arr.shape} ({mb:.0f} MB) | {info['minutes']} phut", flush=True)
print("\n>>> XONG. Save Version -> Dataset 'aic-asr-emb'.", flush=True)
print(">>> Sau khi tai ve: dat vao aic-system/artifacts/asr_emb/, chay lai build_faiss.py", flush=True)

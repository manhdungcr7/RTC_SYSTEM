"""Verify P3/P4 KHÔNG cần nạp model nặng (torch/transformers) — test logic thuần
+ kết nối Milvus/ES thật. Chạy: python aic-system/scripts/verify_p3.py (từ ROOT
repo, hoặc `cd aic-system && python scripts/verify_p3.py`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # aic-system/ lên sys.path

import numpy as np

print("=" * 60, "\n[1] core.fusion.rrf — rank-list giả lập\n", "=" * 60)
from core.fusion import Hit, dedup_by_video, rrf

rl1 = ["a", "b", "c", "d"]
rl2 = ["c", "a", "e", "b"]
fused = rrf([rl1, rl2], k=60, weights=[1.0, 0.5])
order = sorted(fused, key=lambda i: -fused[i])
print("  fused order:", order)
assert order[0] in ("a", "c"), "id hạng cao ở cả 2 list phải lên đầu"
print("  OK")

print("=" * 60, "\n[2] core.fusion.dedup_by_video\n", "=" * 60)
hits = [Hit(id=f"v1:{i:06d}", video="v1", n=i, frame_idx=i, score=1.0 - i * 0.01) for i in range(20)]
hits += [Hit(id=f"v2:{i:06d}", video="v2", n=i, frame_idx=i, score=0.5) for i in range(3)]
d = dedup_by_video(hits, max_per_video=8)
n_v1 = sum(1 for h in d if h.video == "v1")
print(f"  v1 giữ lại {n_v1}/20 (kỳ vọng 8)")
assert n_v1 == 8
print("  OK")

print("=" * 60, "\n[3] core.submit — validate/to_csv_text\n", "=" * 60)
from core import submit as S
rows = S.rows_kis(hits[:5])
print("  rows_kis:", rows)
errs = S.validate(rows, "kis")
print("  errors:", errs)
assert errs == []
bad = S.validate([["L21_V001.mp4", 5]], "kis")
print("  bad (nên có lỗi .mp4):", bad)
assert bad
print("  OK")

print("=" * 60, "\n[4] core.media_index — glob đĩa thật\n", "=" * 60)
from core.media_index import MediaIndex
mi = MediaIndex().build()
p = mi.resolve_frame_path("L21_V001", 1)
print("  resolve_frame_path(L21_V001, 1):", p, "| exists:", p.exists() if p else None)
assert p is not None and p.exists()
pts = mi.pts_time("L21_V001", 1)
print("  pts_time:", pts)
assert pts is not None
mp4 = mi.resolve_video_path("L21_V001")
print("  resolve_video_path:", mp4, "| exists:", mp4.exists() if mp4 else None)
nearby = mi.nearby_ns("L21_V001", 5, 3)
print("  nearby_ns(5, window=3):", nearby)
print("  OK")

print("=" * 60, "\n[5] Milvus repo — kết nối thật, search vector ngẫu nhiên\n", "=" * 60)
from core.repositories.milvus_repo import MilvusRepo
mr = MilvusRepo()
rnd = np.random.randn(1024).astype(np.float32)
rnd /= np.linalg.norm(rnd)
res = mr.search("metaclip2", rnd, 5)
print("  search metaclip2 top5 id:", res)
assert len(res) == 5
meta = mr.fetch_by_ids("metaclip2", res)
print("  fetch_by_ids:", meta)
assert len(meta) == 5
ids, ns, fidx, vecs = mr.fetch_video_vectors("metaclip2", "L21_V001")
print(f"  fetch_video_vectors(L21_V001): {len(ids)} keyframe, vecs.shape={vecs.shape}")
assert len(ids) > 0 and vecs.shape[0] == len(ids)
print("  OK")

print("=" * 60, "\n[6] ES repo — kết nối thật, search OCR\n", "=" * 60)
from core.repositories.es_repo import EsRepo
er = EsRepo()
ocr_res = er.search_frames("ocr_text", "tin tức", 5)
print("  search_frames(ocr_text, 'tin tức') top5:", ocr_res)
asr_res = er.search_asr("tin tức", 5)
print("  search_asr('tin tức') top5:", asr_res)
print("  OK")

print("=" * 60, "\n[7] core.temporal — DP trên 1 video thật (2 sự kiện = vector ngẫu nhiên)\n", "=" * 60)
from core.temporal import search_temporal
ev_vecs = np.random.randn(2, 1024).astype(np.float32)
ev_vecs /= np.linalg.norm(ev_vecs, axis=1, keepdims=True)
results = search_temporal(ev_vecs, mr, "metaclip2", per_event=500, topk=5)
print(f"  {len(results)} ứng viên, ví dụ đầu tiên:",
      (results[0][0], [(h.video, h.n) for h in results[0][1]]) if results else None)
if results:
    ns_seq = [h.n for h in results[0][1]]
    assert ns_seq == sorted(ns_seq), "frame phải tăng dần theo thời gian"
print("  OK")

print("\n>>> TẤT CẢ KIỂM TRA (không cần torch/transformers) ĐỀU QUA.")

"""Verify _text_bonus_matrix + es_repo scoped methods — KHÔNG cần model, chỉ cần
Milvus/ES thật đang chạy."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.media_index import MediaIndex
from core.repositories.es_repo import EsRepo
from core.repositories.milvus_repo import MilvusRepo
from core.temporal import _text_bonus_matrix, _normalize01

print("[1] _normalize01")
print(" ", _normalize01({"a": 1.0, "b": 3.0, "c": 5.0}))
print(" ", _normalize01({}))
print(" ", _normalize01({"a": 2.0}))

print("[2] es_repo.search_frames_scored + search_asr_in_video (video that)")
mi = MediaIndex().build()
er = EsRepo()
mr = MilvusRepo()

# lay 1 video that co OCR/ASR de test (bat ky video nao trong metaclip2)
ids, ns, fidx, vecs = mr.fetch_video_vectors("metaclip2", "L21_V001")
print(f"  video L21_V001: {len(ids)} keyframe")

ocr = er.search_frames_scored("ocr_text", "tin tuc", "L21_V001", 50)
print(f"  ocr_hits cho 'tin tuc' trong L21_V001: {len(ocr)} frame khop")

asr = er.search_asr_in_video("L21_V001", "tin tuc", 50)
print(f"  asr_segs cho 'tin tuc' trong L21_V001: {len(asr)} doan khop")

print("[3] _text_bonus_matrix full")
bonus = _text_bonus_matrix(er, mi, "L21_V001", ids, ns, ["tin tuc thoi su"])
print(f"  bonus shape: {bonus.shape}, max: {bonus.max():.4f}, nonzero cols: {(bonus[0] > 0).sum()}")
print("OK")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.es_repo import EsRepo

er = EsRepo()

full_text = "Khoảnh khắc đầu tiên cắt củ năng."
print(f"Query dung trong temporal.py: {full_text!r}\n")

scored = er.search_frames_scored("ocr_text", full_text, "L26_V179", 200)
print(f"So frame khop trong L26_V179: {len(scored)}")
for doc_id, score in sorted(scored.items(), key=lambda kv: -kv[1])[:15]:
    print(f"  {doc_id}  score={score:.3f}")

print("\n--- so sanh: chi query 'cu nang' (khong co khung cau) ---")
scored2 = er.search_frames_scored("ocr_text", "củ năng", "L26_V179", 200)
print(f"So frame khop: {len(scored2)}")
for doc_id, score in sorted(scored2.items(), key=lambda kv: -kv[1])[:15]:
    print(f"  {doc_id}  score={score:.3f}")

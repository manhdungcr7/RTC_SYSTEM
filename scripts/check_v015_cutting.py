import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.es_repo import EsRepo

er = EsRepo()
scored = er.search_frames_scored("ocr_text", "cắt", "L26_V015", 200)
for doc_id, score in sorted(scored.items(), key=lambda kv: -int(kv[0].split(":")[-1]))[:200]:
    n = int(doc_id.split(":")[-1])
    print(f"  n={n:4d}  score={score:.2f}")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.repositories.es_repo import EsRepo

er = EsRepo()
for term in ["nấm", "củ năng", "đậu hủ", "bếp", "lửa"]:
    scored = er.search_frames_scored("ocr_text", term, "L26_V015", 200)
    top = sorted(scored.items(), key=lambda kv: -kv[1])[:5]
    print(f"{term!r}: {top}")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.query_service import strip_temporal_framing
from core.repositories.es_repo import EsRepo

er = EsRepo()

events = [
    "Khoảnh khắc đầu tiên thấy cắt nấm.",
    "Khoảnh khắc đầu tiên cắt củ năng.",
    "Khoảnh khắc đầu tiên cắt đậu hủ.",
    "Khoảnh khắc chảo đặt lên bếp, đầu bếp mở lửa và thấy lửa bắt đầu xuất hiện",
]

for e in events:
    cleaned = strip_temporal_framing(e)
    print(f"{e!r}\n  -> {cleaned!r}")
    scored = er.search_frames_scored("ocr_text", cleaned, "L26_V179", 200)
    top = sorted(scored.items(), key=lambda kv: -kv[1])[:5]
    print(f"  L26_V179 top matches: {top}")
    print()

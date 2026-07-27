import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from core import config as C
from core.media_index import MediaIndex
from core.query_encoders import MetaClip2Encoder
from core.query_service import strip_temporal_framing
from core.repositories.es_repo import EsRepo
from core.repositories.milvus_repo import MilvusRepo
from core.temporal import search_temporal

mc = MetaClip2Encoder()
mr = MilvusRepo()
er = EsRepo()
mi = MediaIndex().build()

events_raw = [
    "Khoảnh khắc đầu tiên thấy cắt nấm.",
    "Khoảnh khắc đầu tiên cắt củ năng.",
    "Khoảnh khắc đầu tiên cắt đậu hủ.",
    "Khoảnh khắc chảo đặt lên bếp, đầu bếp mở lửa và thấy lửa bắt đầu xuất hiện",
]
events = [strip_temporal_framing(e) for e in events_raw]
event_vecs = mc.encode(events)

for ocr_w in (0.25, 1.0, 2.0, 4.0, 8.0):
    C.OCR_WEIGHT["trake"] = ocr_w
    results = search_temporal(event_vecs, mr, "metaclip2", per_event=1500, topk=5,
                               event_texts=events, es_repo=er, media_index=mi)
    print(f"\n=== OCR_WEIGHT[trake]={ocr_w} ===")
    for total, hits in results[:5]:
        ns = [h.n for h in hits]
        mark = " <<<< DUNG (L26_V015)" if hits[0].video == "L26_V015" else ""
        print(f"  {hits[0].video} score={total:.3f} n={ns}{mark}")

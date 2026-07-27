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
from core.temporal import _text_bonus_matrix

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
print("Events cleaned:", events)
event_vecs = mc.encode(events)

for video in ("L26_V015", "L26_V179"):
    ids, ns, fidx, vecs = mr.fetch_video_vectors("metaclip2", video)
    sub_visual = event_vecs @ vecs.T
    bonus = _text_bonus_matrix(er, mi, video, ids, ns, events)
    sub = sub_visual + bonus

    print(f"\n=== {video} ({len(ids)} keyframe) ===")
    for j in range(4):
        best_visual_idx = int(np.argmax(sub_visual[j]))
        best_total_idx = int(np.argmax(sub[j]))
        print(f"  E{j+1}: max thi giac thuan={sub_visual[j].max():.4f} (n={ns[best_visual_idx]}) | "
              f"max co bonus={sub[j].max():.4f} (n={ns[best_total_idx]}) | "
              f"bonus tai do={bonus[j, best_total_idx]:.4f}")

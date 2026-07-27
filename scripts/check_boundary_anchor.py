import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.query_service import strip_temporal_framing
from core.repositories.milvus_repo import MilvusRepo

# nap encoder that (dung lai tien trinh backend dang chay se nhanh hon nhung
# script nay doc lap de debug don gian)
from core.query_encoders import MetaClip2Encoder

mc = MetaClip2Encoder()
mr = MilvusRepo()

e1 = strip_temporal_framing("Khoảnh khắc đầu tiên thấy cắt nấm.")
e4 = strip_temporal_framing("Khoảnh khắc chảo đặt lên bếp, đầu bếp mở lửa và thấy lửa bắt đầu xuất hiện")
print(f"E1 cleaned: {e1!r}")
print(f"E4 cleaned: {e4!r}")

v1 = mc.encode([e1])[0]
v4 = mc.encode([e4])[0]

for per_event in (1500, 5000, 20000):
    vids1 = mr.video_set_from_topk("metaclip2", v1, per_event)
    vids4 = mr.video_set_from_topk("metaclip2", v4, per_event)
    print(f"per_event={per_event}: L26_V015 trong E1-top? {'L26_V015' in vids1} | "
          f"trong E4-top? {'L26_V015' in vids4} | "
          f"trong CA HAI (giao)? {'L26_V015' in (vids1 & vids4)}")

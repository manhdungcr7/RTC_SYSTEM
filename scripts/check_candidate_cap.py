import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config as C
from core.query_service import strip_temporal_framing
from core.repositories.milvus_repo import MilvusRepo
from core.query_encoders import MetaClip2Encoder

mc = MetaClip2Encoder()
mr = MilvusRepo()

e1 = strip_temporal_framing("Khoảnh khắc đầu tiên thấy cắt nấm.")
e4 = strip_temporal_framing("Khoảnh khắc chảo đặt lên bếp, đầu bếp mở lửa và thấy lửa bắt đầu xuất hiện")
v1 = mc.encode([e1])[0]
v4 = mc.encode([e4])[0]

v_first = mr.videos_from_topk("metaclip2", v1, 1500)
v_last = mr.videos_from_topk("metaclip2", v4, 1500)
inter = set(v_first) & set(v_last)
print(f"|v_first|={len(v_first)} |v_last|={len(v_last)} |inter|={len(inter)}")

if len(inter) >= 20:
    cand = [v for v in v_first if v in inter]
else:
    cand = list(dict.fromkeys(v_first + v_last))
print(f"cand_videos truoc cap: {len(cand)}")
capped = cand[:C.MAX_TRAKE_CANDIDATES]
print(f"cand_videos SAU cap({C.MAX_TRAKE_CANDIDATES}): {len(capped)}")
print(f"L26_V015 trong danh sach truoc cap? {'L26_V015' in cand}"
      f" | vi tri: {cand.index('L26_V015') if 'L26_V015' in cand else 'KHONG CO'}")
print(f"L26_V015 con trong danh sach SAU cap? {'L26_V015' in capped}")
print(f"L26_V063 (ket qua moi) vi tri: {cand.index('L26_V063') if 'L26_V063' in cand else 'KHONG CO'}")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.media_index import MediaIndex

mi = MediaIndex().build()

pairs = [
    ("17-r2", "L30_V015", 70), ("17-r3", "L25_V077", 106), ("17-r4", "L21_V019", 392), ("17-r5", "L21_V011", 37),
    ("15qa-r2", "L25_V008", 109), ("15qa-r3", "L25_V085", 143), ("15qa-r4", "L29_V003", 246), ("15qa-r5", "L25_V040", 120),
]
for qnum, video, n in pairs:
    p = mi.resolve_frame_path(video, n)
    print(f"{qnum}\t{video}:{n}\t{p}")

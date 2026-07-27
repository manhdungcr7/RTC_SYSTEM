import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.media_index import MediaIndex

mi = MediaIndex().build()

pairs = [
    ("1", "L21_V024", 339), ("2", "L21_V029", 157), ("5", "L27_V014", 34),
    ("6", "L26_V378", 128), ("7", "L29_V023", 476), ("8", "L22_V030", 329),
    ("9", "L28_V022", 136), ("10", "L30_V017", 54), ("11", "L30_V057", 42),
    ("12", "L26_V460", 52), ("13", "L30_V095", 44), ("14", "L21_V027", 399),
    ("17", "L29_V010", 399), ("20", "L26_V004", 13), ("21", "L21_V002", 363),
    ("23", "L22_V022", 283), ("24", "L23_V007", 62), ("25", "L23_V007", 62),
    ("15qa", "L30_V033", 42), ("19qa", "L27_V010", 145), ("22qa", "L26_V404", 153),
]
for qnum, video, n in pairs:
    p = mi.resolve_frame_path(video, n)
    print(f"{qnum}\t{video}:{n}\t{p}")
